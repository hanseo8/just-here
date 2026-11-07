# 백업 삭제 정리본 및 복구 보호 · 2026-11-07

로컬 구현/임시 백업 검증 완료, 운영 미배포. 운영 백업과 실 사용자 기록은 변경하거나 삭제하지 않았다.

## 기능
- 삭제 시 UID·기기·연결 세션의 원문 대신 SHA-256과 증가하는 revision을 남긴다. 저장 실패 시 프로필/기기 연결/폐기 목록을 함께 롤백한다.
- 관리자 토큰/활성 2FA가 적용되는 registry API와 내려받기 버튼으로 최소 목록만 내보낸다. 목록 자체도 비공개로 보관한다.
- directory snapshot, rewards ZIP, storage JSON 및 old/current 병합 복구에 별도로 준비한 최신 목록을 필수 적용한다. 백업 자신의 과거 목록을 신뢰 근거로 삼지 않는다.
- UID뿐 아니라 기기 전용 이벤트/익명 세션, 네이티브 로그인 시도, 진행 중 삭제 저널을 다룬다. 다른 계정과 공유된 식별자, 금융/인증 기록, 미분류 파일, 손상 자료는 거절한다.
- 대상은 반드시 새 폴더. 원본과 겹침·기존 대상·심볼릭 링크를 거절한다. 정리본의 파일별 해시/적용한 목록 지문·revision을 보고서로 남긴다.
- users.json에는 최신 폐기 목록을 반영한다. reward-only ZIP 출력은 별도 deletion-registry.json 및 점검 표시를 남긴다. 계정 파일/서명 키를 같은 목록 기준으로 복구하고 검사하기 전에는 서비스에 사용하지 않는다.
- 시작 시 별도 deletion-registry.json도 읽어 폐기 목록을 합친다. 오래된 프로필이 목록과 충돌하면 데이터 덮어쓰기/재접속을 차단한다.
- 실제 운영 적용 도구는 현재 users 저장소와 목록 지문을 확인한다. 점검/진행 요청 종료 후 프로세스 간 잠금을 획득하고 다시 로드해 확인하므로 삭제와 복구를 동시에 진행하지 못한다.

## 명령 예시 (실행은 운영자 검토 후)
```text
python scripts/sanitize-deletion-backup.py OLD_SNAPSHOT NEW_SANITIZED_DIRECTORY --deletion-registry CURRENT_REGISTRY.json
python scripts/restore-rewards.py rewards-backup.zip NEW_RESTORE_DIRECTORY --deletion-registry CURRENT_REGISTRY.json
python scripts/restore-storage.py storage-backup.json --stage NEW_RESTORE_DIRECTORY --deletion-registry CURRENT_REGISTRY.json
python scripts/merge-storage.py OLD.json CURRENT.json --stage NEW_DIRECTORY --deletion-registry CURRENT_REGISTRY.json
```

원본 백업 디렉터리 밖에서, 복구 적용 직전에 내보낸 CURRENT_REGISTRY.json을 사용한다. 오프라인 도구는 외부의 전역 최신성을 스스로 증명할 수 없다. 운영 적용 단계의 live registry 지문 대조가 필요하며 수동 파일 복사로 이 절차를 우회하면 보호를 보장할 수 없다.

## 검사
- check-deletion-backup: 원본 바이트 보존, 새 정리본/ZIP에서 삭제 계정 제외, 다른 계정/이벤트/원장 보존, 복구 후 예전 토큰 거절, guard-only 부팅의 폐기 목록, 누락/과거 목록/손상/미분류 자료/공유 식별자/재사용 대상 거절, 병합 시 부활 방지, 프로세스 간 잠금.
- check-account-deletion-executor, check-deleted-identity: 삭제 재개·목록 저장·토큰 차단.
- check-storage-restore/merge, check-rewards-api/payouts: 기존 백업·원장·지급 회귀.
- 모든 실제 삭제·정리본 생성은 TemporaryDirectory 안의 가상 데이터로만 검사.

## 아직 전체 삭제 완료가 아닌 이유
- 정리본을 만들어도 원본 백업은 그대로 남는다. 원본 교체·파기나 외부/Render 관리 스냅샷까지 처리했다는 의미가 아니다.
- 이번 도구가 다루지 않는 외부 사본·업로드 원본·서명 키·임의 형식의 백업은 별도 목록과 정책이 필요하다. 미분류 파일은 무시하지 않고 차단한다.
- 기록별 보존 근거·기한과 실제 원본 파기, 최소 폐기 목록의 보존 정책이 확정되지 않았다. 금융/인증 기록이 있는 고객의 삭제는 별도 정책/분리 실행이 남는다.
- active_data_deleted/backup_status=pending/full_deletion_complete=false를 유지한다. 최종 completed 상태나 원본 자동 삭제를 추가하지 않았다.
