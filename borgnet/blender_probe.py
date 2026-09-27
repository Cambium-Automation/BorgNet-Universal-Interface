"""Executed by Blender in background mode with Python auto-execution disabled."""
import json
import bpy

objects = []
for item in list(bpy.data.objects)[:300]:
    objects.append({'name': item.name, 'type': item.type,
                    'parent': item.parent.name if item.parent else None,
                    'dimensions_m': [round(float(value), 5) for value in item.dimensions]})
report = {'scene': bpy.context.scene.name if bpy.context.scene else None,
          'object_count': len(bpy.data.objects), 'objects': objects,
          'truncated': len(bpy.data.objects) > len(objects),
          'auto_execute_enabled': False}
print('BORGNET_SCENE_JSON:' + json.dumps(report, ensure_ascii=False))
