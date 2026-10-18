import pytest


@pytest.mark.parametrize('width,height', [(1280,720),(768,432),(1920,1080)])
def test_exact_widescreen_dimensions(width,height):
    from video_ai.planning.start_images import validate_dimensions
    assert validate_dimensions(width,height) == (width,height)


@pytest.mark.parametrize('width,height', [(True,720),(1024,1024),(1280,719),(0,0),(32,18),(1280.0,720)])
def test_invalid_dimensions_rejected(width,height):
    from video_ai.planning.start_images import validate_dimensions
    with pytest.raises(ValueError): validate_dimensions(width,height)


def board():
    return dict(run_id='test',global_visual=dict(style='cinematic',color_palette='blue',lighting='night',
        entities=[dict(entity_id='water',description='water surface')]),shots=[
        dict(shot_id='shot_0001',start_frame=0,primary_unit_id='u1',image_prompt='Full original words.',entity_ids=[],
            bindings=[dict(unit_id='u2',quantization_edge=True)],
            visual_requirements=[dict(requirement_id='r1',unit_id='u1',source_quote='tree'),dict(requirement_id='r2',unit_id='u2',source_quote='water')]),
        dict(shot_id='shot_0002',start_frame=10,primary_unit_id='u2',image_prompt='Water reflected.',entity_ids=['water'],bindings=[],
            visual_requirements=[dict(requirement_id='r3',unit_id='u2',source_quote='water')])])


def test_primary_and_foreign_edges_bind_corresponding_scene():
    from video_ai.planning.start_images import requirement_images
    identities={'shot_0001':{'sha256':'tree'},'shot_0002':{'sha256':'water'}}
    items=requirement_images(board(),identities)
    assert len(items)==3 and items[1]['requirement_index']==1
    assert items[1]['role']=='quantization_edge_preview' and items[1]['image_identity']==identities['shot_0002']
    assert items[0]['role']=='primary'


def test_prompt_preserves_full_original_and_shared_description():
    from video_ai.planning.start_images import image_parameters
    b=board();params=image_parameters(b['shots'][1],b['global_visual'],1280,720)
    assert params['positive'].startswith('Water reflected.') and 'water surface' in params['positive']
    assert params['seed']==812045847300607 and params['batch']==1 and params['steps']==25
    assert 'color, colored' not in params['negative']


def test_reviewed_static_direction_is_first_and_preserves_original_prompt():
    from video_ai.planning.start_images import image_parameters
    b=board()
    direction=dict(positive='Artificial lamps reflected on water at night.',negative='sun, daylight')
    params=image_parameters(b['shots'][1],b['global_visual'],1280,720,direction=direction)
    assert params['positive'].startswith('Artificial lamps reflected on water at night.')
    assert 'Water reflected.' in params['positive'] and 'water surface' in params['positive']
    assert params['negative'].endswith('sun, daylight')
    assert params['seed']==812045847300607


def test_directions_cannot_bind_neighbor_scene_or_unknown_shot():
    from video_ai.planning.start_images import validate_directions
    b=board()
    data=dict(schema_version=1,run_id='test',storyboard_identity={},review_basis_identity={},
              shots={'shot_0001':dict(positive='Leafy tree.',negative='bare tree',reason='Missing leaves.',requirement_ids=['r2'])})
    with pytest.raises(ValueError):validate_directions(data,b)


@pytest.mark.parametrize('bad', ['unknown','shot','entity','bool','relative'])
def test_input_map_rejects_unknown_and_unsafe_inputs(bad):
    from video_ai.planning.start_images import validate_input_map
    data=dict(schema_version=1,run_id='test',shots={},entities={})
    if bad=='unknown': data['extra']=1
    if bad=='shot': data['shots']['shot_9999']='D:/picture.png'
    if bad=='entity': data['entities']['../escape']='D:/picture.png'
    if bad=='bool': data['schema_version']=True
    if bad=='relative': data['shots']['shot_0001']='picture.png'
    with pytest.raises(ValueError):validate_input_map(data,board())
