"""Compile model-facing English separately from immutable source grounding."""
import re

from .storyboard import depiction_anchor

VISUAL_MODE = 'model_visual_v2'
VOYAGER_APPEARANCE = ('A single Voyager spacecraft with a white parabolic dish antenna, '
    'gold foil body, slender antenna booms and a cylindrical RTG boom')
MODEL_NEGATIVE_SUFFIX = ', diagram, schematic, technical drawing, labeled illustration, multiple panels, contact sheet, color chart, text, letters, captions'
VOYAGER_NEGATIVE_SUFFIX = ', multiple spacecraft, duplicate spacecraft, solar panels, humanoid robot, cockpit, engine exhaust'
VOYAGER_ALIASES = ('旅行者1号','旅行者一号','旅行者2号','旅行者二号','飞船','探测器')


def english_visual(text, *, min_words=3):
    if (not isinstance(text,str) or not text.strip() or not text.isascii()
        or len(text)>800 or len(re.findall(r'[A-Za-z]+',text))<min_words
        or re.search(r'(color_palette|entity_ids|source_quote|style\s*:|lighting\s*:|Camera path\s*:)',text)):
        raise ValueError('model visual description must be concrete English, without source/metadata labels')
    return text.strip()


def primary_requirement(shot):
    matches=[r for r in shot['visual_requirements'] if r['unit_id']==shot['primary_unit_id']]
    if len(matches)!=1:raise ValueError('one primary source requirement required')
    return matches[0]


def presentation(shot,field):
    req=primary_requirement(shot)
    anchor=depiction_anchor(req,source_quote=req['source_quote'])
    value=shot[field]
    if not value.startswith(anchor):raise ValueError('visual source anchor differs')
    value=value[len(anchor):]
    if field=='video_prompt':
        suffix=' Camera path: '+shot['camera_motion']+'.'
        if not value.endswith(suffix):raise ValueError('visual camera path differs')
        value=value[:-len(suffix)]
    return english_visual(value)


def validate_scene_subject(shot,scene):
    quote=primary_requirement(shot)['source_quote']
    # These are admission hints, not a claim that pixels match the text. They
    # catch the observed wholesale appearance-copy failure before inference.
    terms=(('木星',r'\bjupiter\b'),('土星',r'\bsaturn\b'),('木卫一',r'\bio\b'),
        ('火山',r'volcan|eruption|plume'),('唱片',r'\brecord\b|\bdisc\b'),
        ('望远镜',r'telescope|distant.*point|point.*light'))
    for source,pattern in terms:
        if source in ('木星','土星'):
            # A parent planet in ownership (Titan) or a list of gravity-assist
            # examples is context, not a requirement to render every planet.
            if '卫星' in quote or sum(k in quote for k in ('木星','土星'))>1:continue
            direct=(quote.startswith(source) or any(k in quote for k in
                ('飞掠'+source,'飞过'+source,'抵达'+source,'驶向'+source,'掠过'+source,source+'环')))
            if not direct:continue
        if source=='唱片' and '土星环' in quote and any(k in quote for k in ('仿佛','像','好似')):continue
        if source in quote and not re.search(pattern,scene,re.I):
            raise ValueError('missing original visual subject '+source+' in English scene; describe the scene, not copied probe anatomy')


def visible_entity(entity,scene):
    """A referenced entity may be narrative context, not a visible object."""
    names=re.findall(r'[A-Za-z]{2,}',entity['entity_id'].lower())
    names=[n for n in names if n not in ('entity','subject','id')]
    if any(re.search(r'\b'+re.escape(name)+r'\b',scene,re.I) for name in names):return True
    physical={'bird','dog','cat','person','man','woman','lake','river','tree','house','car',
        'spacecraft','probe','moon','planet','record','disc','volcano','volcanic'}
    description=set(re.findall(r'[a-z]+',entity['description'].lower()))
    scene_words=set(re.findall(r'[a-z]+',scene.lower()))
    return bool(physical & description & scene_words)


def render_model_prompt(shot,global_visual,kind):
    if kind not in ('image','video'):raise ValueError('image or video required')
    scene=presentation(shot,kind+'_prompt')
    validate_scene_subject(shot,scene)
    req=primary_requirement(shot)
    subject=req['subject'] or ''
    # Explicit Voyager names are enough; generic craft aliases apply only when
    # the frozen catalog actually identifies Voyager. Do not turn Io/planets
    # into probes just because a planner incorrectly attached a probe entity ID.
    catalog=' '.join(e['entity_id']+' '+e['description']+' '+' '.join(e.get('source_quotes',[])) for e in global_visual['entities'])
    voyager=(any(a in subject for a in VOYAGER_ALIASES[:4]) or
        re.search(r'\bVoyager\b',scene,re.I) is not None or
        (subject in VOYAGER_ALIASES[4:] and ('Voyager' in catalog or '旅行者' in catalog)))
    appearance=VOYAGER_APPEARANCE if voyager else ''
    if voyager:
        # The planner may repeat frozen anatomy. Give CLIP one physical
        # description, reserving its early tokens for the scene and setting.
        scene=', '.join(part.strip() for part in scene.split(',') if not re.search(
            r'^(Voyager\s*[12]?\s*$|uncrewed probe|white .*antenna|gold foil body|long thin booms|cylindrical RTGs)',part.strip(),re.I))
    if not voyager:
        entities={e['entity_id']:e for e in global_visual['entities']}
        appearance=', '.join(english_visual(entities[eid]['description'],min_words=1) for eid in shot['entity_ids']
            if visible_entity(entities[eid],scene))
    # Validate frozen style directions, but keep physical colors in the scene.
    # A global metallic/gold palette must not recolor Io or turn Jupiter into
    # a stylized ring diagram. Metadata stays in the storyboard evidence.
    for k in ('color_palette','lighting'):english_visual(global_visual[k],min_words=1)
    style=english_visual(global_visual['style'],min_words=1)
    # Scene first; hardware before style. Never feed literal fact anchors,
    # source quotes, entity identifiers or dictionary labels to CLIP/UMT5.
    parts=[appearance,scene,style] if voyager else [scene,appearance,style]
    if kind=='image':parts+=['Single cinematic view, realistic photographic reconstruction']
    if kind=='video':parts += ['Preserve the first-frame subject geometry and background. '+shot['camera_motion']+'.']
    return '. '.join(p.strip().rstrip('.') for p in parts if p)+'.'


def validate_english_content(content):
    for key in ('style','color_palette','lighting'):english_visual(content['global_visual'][key],min_words=1)
    for entity in content['global_visual']['entities']:english_visual(entity['description'],min_words=1)
    for shot in content['shots']:
        primary=dict(shot,primary_unit_id=shot['visual_requirements'][0]['unit_id'])
        for field in ('image_prompt','video_prompt'):
            scene=presentation(primary,field);validate_scene_subject(primary,scene)


MODEL_VISUAL_INSTRUCTIONS = (
    'MODEL_VISUAL_V2: Source facts/quotes are evidence, NOT diffusion prompts. '
    'Generate clear English scene descriptions; do not echo Chinese facts or source anchors in them. '
    'Translate meaning into one visible subject, physical setting, composition and plausible action. '
    'Use the ordered original_source_catalog to resolve pronouns, ellipsis and abstract narration. '
    'The exact original quote has priority over faulty extracted interpretations; never copy an unrelated entity. '
    'For abstract narration hold or extend the last grounded scene; do not literalize letters, silence, time, decisions or communication into rooms, robots, charts or visible light beams. '
    'If the source cannot be depicted faithfully, set needs_finer_audio=true instead of inventing an event. '
    'A telescope point of light is a distant celestial object, not a radio beam. '
    'The renderer adds Voyager hardware separately; do NOT copy its long anatomy into the 160-character scene description. '
    'Describe the actual setting and action, with the visible subject first. '
    'Examples: "Voyager 1, isolated uncrewed probe coasting through dark interstellar space, wide view."; '
    '"Voyager 1 passes above Jupiter, enormous striped gas giant below, black space background."; '
    '"Io volcanic moon, yellow sulfur surface, white eruption plume rising into black space."; '
    '"Close view of a single gold-plated copper phonograph record, fine circular grooves, black background." '
    'For Voyager entity descriptions use: "Uncrewed probe, white dish antenna, gold foil body, long thin booms, cylindrical RTGs." '
    'No humanoid form, cabin, passengers, solar panels or propulsion flames in coasting scenes. '
    'Voyager 1 and Voyager 2 are different probes with the same hardware design. '
    'Planets, moons, Earth scenes and record details should be depicted themselves when the quote calls for them. '
    'Use concrete English global style/palette/lighting and entity descriptions; entity IDs and source quotes stay unchanged. '
    'Keep image and motion descriptions compatible; respect negation, quantities, time and ordering. '
    'Avoid dramatic invented motions; choose slow restrained camera movement.'
)
