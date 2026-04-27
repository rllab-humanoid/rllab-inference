"""
전체 에피소드 실행 스크립트.
Agent (Gemma 4) → Robot CLI → Skill Policy 전체 파이프라인.

사용:
    python run_episode.py --zone A
    python run_episode.py --zone A --dummy   # 더미 환경 (실제 로봇 없이)
"""
import argparse

from agent.robot_cli import RobotCLI


def run_episode(zone: str, dummy: bool = False):
    cli = RobotCLI()
    
    # Step 1: 모니터 해석 (Gemma 4 vision)
    # monitor_instruction = cli.view()
    
    # Step 2: 메인 루프
    # while not done:
    #     scene = cli.status()           # YOLO bbox
    #     command = agent.decide(scene)   # Gemma 4 → CLI 커맨드
    #     result = cli.execute_skill(command)
    #     if command == "done":
    #         break
    
    raise NotImplementedError


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--zone", choices=["A", "C", "D"], required=True)
    parser.add_argument("--dummy", action="store_true", help="더미 환경 (로봇 없이)")
    args = parser.parse_args()
    run_episode(args.zone, args.dummy)
