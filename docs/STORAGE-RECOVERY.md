# 사용자·이벤트 백업 복구

`/health`의 `persistent=true`는 저장 경로가 실제 마운트라는 뜻이다. 기존 사용자·이벤트가 복원되었거나 재시작 뒤 같은 기록이 남았다는 뜻은 아니다.

## 로컬 검증과 복원 준비

관리자 `/v1/admin/storage/backup` 응답을 비공개 파일로 보관한다. 복구 도구는 백업의 오류 상태, 파일 목록, JSON·JSONL 형식을 먼저 검사한다. 식별자와 문서 내용은 출력하지 않는다.

```powershell
python -B scripts/restore-storage.py data/_backup-/20261003-before-disk/backup.json
python -B scripts/restore-storage.py data/_backup-/20261003-before-disk/backup.json --stage data/_backup-/20261003-before-disk/NEW_RESTORE_DIRECTORY
python -B scripts/restore-storage.py data/_backup-/20261003-before-disk/backup.json --compare data/_backup-/20261003-before-disk/NEW_RESTORE_DIRECTORY
```

`--stage`의 상위 폴더는 존재해야 하며 대상 폴더는 없어야 한다. 기존 폴더·심볼릭 링크에는 복원하지 않는다. 쓰기 실패 시 부분 복원 폴더를 남기고 실패하며, 같은 폴더로 재시도하지 않는다. 출력 SHA-256은 백업과 복원 파일을 비교하기 위한 값이며 백업 출처의 진위를 보장하지 않는다.

Linux에서는 새 폴더·파일 권한을 700·600으로 제한한다. Windows에서는 상위 폴더의 ACL을 상속하므로 백업 폴더 접근 권한을 별도로 관리한다.

2026-10-04 로컬 리허설: 보관 중인 운영 백업을 `data/_backup-/20261003-before-disk/restored-verified`에 복원하고 사용자·이벤트 파일의 바이트가 모두 일치함을 확인했다. 운영 `/data`에 적용하거나 운영 재시작 보존을 검사한 결과는 아니다.

## 운영 이관

이전 백업과 현재 백업은 다음 명령으로 먼저 오프라인 병합한다. 현재 백업은 오류 없이 확보된 실제 관리자 백업이어야 한다.

```powershell
python -B scripts/merge-storage.py OLD_BACKUP.json CURRENT_BACKUP.json --stage NEW_MERGE_DIRECTORY
python -B -m scripts.check-storage-merge
```

같은 사용자 ID 또는 기기 연결에 서로 다른 값이 있으면 병합을 거절한다. 신규 사용자는 보존하고 이벤트는 두 백업 사이의 중복만 제거한다. 각 백업 내부의 반복 이벤트 수는 유지한다. 메뉴·제휴 카탈로그는 현재 백업을 유지한다. 출력은 건수와 해시이며 사용자 식별자를 포함하지 않는다. 이 명령은 운영 파일을 교체하지 않는다.

1. 현재 `/data`의 사용자·이벤트를 별도로 백업하고 신규 기록 유무를 확인한다.
2. 신규 기록이 있으면 이전 백업으로 덮지 않는다. 사용자 ID 충돌과 이벤트 중복을 조사해 병합 방식을 정한다.
3. 서버 쓰기가 중단된 유지보수 구간에 검증된 파일을 이관한다. 실행 중 프로세스의 사용자 캐시도 있으므로 파일 복사만으로 복구 완료로 판정하지 않는다.
4. 서비스를 재시작하고 UID·통제 이벤트 ID를 확인한다. 해당 파일의 바이트 비교는 신규 쓰기를 잠시 중단한 상태에서 수행한다.
5. 통제 기록을 새로 남긴 뒤 한 번 더 재시작하여 같은 ID와 값이 유지되는지 확인한다.

복구 스크립트는 운영 파일 적용·병합·서비스 재시작을 자동으로 수행하지 않는다. 서명 비밀값과 운영 환경설정은 별도 보관 대상이다. 영수증·Duo·추천 세션의 메모리 저장은 이 도구의 복구 대상이 아니다.

### 2026-10-04 운영 보존 확인

현재 운영 파일은 `/data/recovery-20261004/before.json`에 백업했고, 세 파일의 SHA-256을 같은 폴더 `hashes.json`에 보관했다. Render 서비스 재시작으로 인스턴스가 `qxkxj`에서 `cr4ch`로 바뀐 뒤 `users.json`, `events.jsonl`, `verified-menus.json`의 바이트 해시가 모두 일치했다. 이는 현재 기록의 재시작 보존 확인이다. 이전 휘발 저장소 백업 복원, 영수증·Duo 영구 저장, 보상 운영 배포 완료를 의미하지 않는다.

## 회귀 검사

```powershell
python -B -m scripts.check-storage-restore
```

UTF-8 백업 복원, 파일 바이트 일치, 기존 경로 덮어쓰기 거절, 손상 JSONL·중복 JSON 키·경로 탈출·불완전 백업 거절을 검사한다.
