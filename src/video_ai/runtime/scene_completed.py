"""Read-only reconstruction of the schema-2 scene media completed prefix."""


def validate_scene_completed_prefix(frozen,units,timeline):
    from .scene_media_records import load_scene_media_progress
    # The progress facade admits every extant complete gate in dependency order;
    # it never fills missing markers or touches legacy shot stage state.
    return load_scene_media_progress(frozen,units,timeline)
