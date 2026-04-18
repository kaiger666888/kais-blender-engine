"""scene-layout 客厅场景示例"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from skills.scene_layout.layout_engine import SceneComposer

def main():
    composer = SceneComposer()
    
    # 客厅场景：角色坐在沙发上
    result = composer.compose_living_room(
        character_animation=r"D:\BlenderAgent\animations\motions\sitting_while_laughing_inplace_withskin.fbx",
        position="on:sofa",
        hdri="studio_small_03",
    )
    
    if result.warnings:
        print("WARNINGS:")
        for w in result.warnings:
            print(f"  ⚠️  {w}")
    
    output_path = "/tmp/blender_living_room.py"
    with open(output_path, "w") as f:
        f.write(result.blender_script)
    
    print(f"Script generated: {output_path} ({len(result.blender_script)} chars)")
    
    # 使用方式：
    # python3 -c "import json; print(json.dumps({'script': open('/tmp/blender_living_room.py').read(), 'timeout': 300}))" > /tmp/job.json
    # curl -s -X POST http://192.168.71.38:8080/run/async -H "Content-Type: application/json" -d @/tmp/job.json

if __name__ == "__main__":
    main()
