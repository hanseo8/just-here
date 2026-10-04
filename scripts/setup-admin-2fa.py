"""User-run, offline authenticator setup. Never writes files or changes Render."""
import argparse
import base64
import getpass
import hmac
import secrets
import sys
import time

from backend.app.admin_security import code


def matches(secret, otp, timestamp):
    if len(otp) != 6 or not otp.isascii() or not otp.isdigit():
        return False
    step = int(timestamp) // 30
    return any(hmac.compare_digest(code(secret, s), otp)
               for s in (step - 1, step, step + 1) if s >= 0)


def main(argv=None):
    parser = argparse.ArgumentParser(description='본인 컴퓨터의 개인 터미널에서 인증 앱을 등록합니다.')
    parser.add_argument('--create', action='store_true', help='새 등록 키를 생성합니다. 기존 운영 키를 교체하지 않습니다.')
    args = parser.parse_args(argv)
    if not args.create:
        parser.print_help()
        return 0
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print('개인 대화형 터미널에서만 실행할 수 있습니다. 로그 수집·화면 공유를 종료해 주세요.', file=sys.stderr)
        return 2

    secret = secrets.token_bytes(20)
    encoded = base64.b32encode(secret).decode('ascii')
    print('이 키는 파일에 저장되지 않습니다. 채팅·스크린샷으로 공유하지 마세요.')
    print('인증 앱 → 계정 추가 → 설정 키 직접 입력')
    print('계정 이름: 그냥여기 관리자 / 유형: 시간 기반(TOTP)')
    print('설정 키:', encoded)
    for _ in range(3):
        try:
            otp = getpass.getpass('인증 앱에 표시된 6자리 번호: ').strip()
        except (EOFError, KeyboardInterrupt):
            print('\n등록 확인을 취소했습니다. Render 설정을 변경하지 않았습니다.')
            return 1
        if matches(secret, otp, time.time()):
            print('인증 앱 등록 확인 완료. Render 환경 변수에 직접 입력하세요:')
            print('ADMIN_TOTP_SECRET =', encoded)
            print('ADMIN_REQUIRE_2FA = on')
            print('저장·배포 후 관리자 화면에서 새 번호로 로그인하세요.')
            print('기존 운영 키가 있으면 중단하고 먼저 복구 계획을 확인하세요.')
            return 0
        print('번호가 맞지 않습니다. 휴대폰 자동 시간 설정과 등록 키를 확인하세요.')
    print('등록 미확인. Render에 이 키를 적용하지 마세요.')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
