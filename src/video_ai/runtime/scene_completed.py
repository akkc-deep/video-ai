"""Read-only reconstruction of the schema-2 scene media completed prefix."""


def validate_scene_completed_prefix(frozen,units,timeline):
    from .scene_media_records import _scene_media_base_context,_load_scene_media_progress
    from .scene_revision_records import _context
    # The progress facade admits every extant complete gate in dependency order;
    # it never fills missing markers or touches legacy shot stage state.
    context=_scene_media_base_context(frozen,units,timeline)
    progress=_load_scene_media_progress(context)
    scope=_context.get()
    if scope is not None:
        scope.setdefault('scene_prefixes',{})[frozen.options['run_id']]=context
    return progress


def load_validated_prefix_details(frozen):
    """Use only this call's admitted context, rechecking captured bytes and tools."""
    from .scene_revision_records import _context
    from .production_state import ProductionRefused
    from ..planning.production_scenes import canonical_digest
    scope=_context.get()
    context=scope.get('scene_prefixes',{}).get(frozen.options['run_id']) if scope is not None else None
    if context is None or canonical_digest(context['frozen'].options)!=canonical_digest(frozen.options):
        raise ProductionRefused('no validated scene prefix in current invocation')
    store=context['store'];store.verify_captured_bytes();store.verify_tools()
    candidate=context.get('validated_candidate');receipt=context.get('validated_delivery')
    if receipt is not None:
        from .scene_delivery_files import validate_completed
        receipt=validate_completed(context,candidate,context['validated_final_acceptance'])
    return dict(candidate=candidate,delivery=receipt)
