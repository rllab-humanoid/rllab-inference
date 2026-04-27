# 작업 흐름

## 데이터 수집 (rllab-data-collection 레포)
1. `python collect.py --skill grasp --operator 이름`
2. 텔레옵으로 데모 수행 → raw HDF5 자동 저장
3. `python tools/inspect.py --episode latest` 로 확인
4. 문제 있으면 삭제 후 재수집

## 학습 (이 레포)
1. raw HDF5 → LeRobot 변환
   ```bash
   python policy/converter.py --input ~/rllab_datasets/session_xxx/ --output ~/lerobot_datasets/skill_grasp/
   ```
2. 학습
   ```bash
   bash policy/train.sh grasp
   ```
3. 평가
   ```bash
   bash policy/eval.sh grasp outputs/train/grasp/best.pt
   ```

## Agent 테스트
1. Gemma 4 서버 시작
   ```bash
   python agent/gemma_server.py
   ```
2. 더미 에피소드 실행
   ```bash
   python scripts/run_episode.py --zone A --dummy
   ```

## YOLO
1. 데이터 라벨링 (Roboflow → perception/data/ 에 export)
2. 학습
   ```bash
   python perception/yolo_train.py --data perception/data/parts.yaml
   ```

## 실험 결과 기록
- Notion Log 페이지에 날짜 + type(실험) + 성공률 기록
- skill별 성공률 추적
