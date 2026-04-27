"""
Robot CLI — Agent가 로봇을 제어하는 인터페이스.
Gemma 4가 이 커맨드들을 호출해서 skill policy를 실행함.

사용 예:
    cli = RobotCLI()
    cli.status()           # YOLO bbox + gripper 상태
    cli.view()             # Gemma 4 vision으로 scene 확인
    cli.execute_skill("approach", target="flange_nut")
    cli.execute_skill("grasp")
"""

SKILLS = {
    "approach":       {"policy": None, "timeout": 10.0, "description": "목표 물체 근처로 이동"},
    "grasp":          {"policy": None, "timeout": 3.0,  "description": "가까운 물체 잡기"},
    "place":          {"policy": None, "timeout": 3.0,  "description": "잡은 물체 놓기"},
    "insert_bolt":    {"policy": None, "timeout": 5.0,  "description": "볼트 peg 삽입"},
    "push_button":    {"policy": None, "timeout": 2.0,  "description": "완료 버튼 누르기"},
    "bimanual_grasp": {"policy": None, "timeout": 5.0,  "description": "타이어 양손 파지"},
    "insert_tire":    {"policy": None, "timeout": 8.0,  "description": "타이어 홀 삽입"},
    "grasp_drill":    {"policy": None, "timeout": 5.0,  "description": "드릴 3손가락 파지"},
    "drill_trigger":  {"policy": None, "timeout": 3.0,  "description": "드릴 트리거 당김"},
}


class RobotCLI:
    def __init__(self):
        # TODO: YOLO, policy pool, ROS2 연결 초기화
        pass

    def status(self) -> dict:
        """YOLO bbox + gripper 상태를 텍스트로 반환.
        
        Returns:
            {"objects": [{"label": "flange_nut", "bbox": [x1,y1,x2,y2], "conf": 0.95}],
             "gripper": {"left": "open", "right": "open"},
             "joint_state": [...]}
        """
        raise NotImplementedError

    def view(self) -> str:
        """Gemma 4 vision으로 현재 카메라 이미지 해석 (확인용).
        
        Returns:
            Gemma 4가 생성한 scene description 문자열
        """
        raise NotImplementedError

    def execute_skill(self, skill_name: str, target: str = None) -> bool:
        """skill policy 실행 → 완료 시그널 반환.
        
        Args:
            skill_name: SKILLS 딕셔너리의 키
            target: 목표 물체 (approach, place 등에서 사용)
            
        Returns:
            True if success, False if timeout/failure
        """
        if skill_name not in SKILLS:
            raise ValueError(f"Unknown skill: {skill_name}")
        # TODO: policy 로드 → 실행 → 완료 감지 → 반환
        raise NotImplementedError

    def done(self):
        """에피소드 종료 선언."""
        pass
