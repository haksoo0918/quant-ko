# ☁️ 오라클 클라우드(OCI) 무인 자동매매 배포 가이드 (왕초보 A to Z)

오라클 클라우드(Oracle Cloud Infrastructure, OCI)의 **평생 무료(Always Free)** 서버를 이용해 내 PC를 켜두지 않고도 24시간 365일 자동매매 봇이 돌아가도록 만드는 단계별 매뉴얼입니다. 명령어는 그대로 복사해서 붙여넣으시면 됩니다.

---

## STEP 1. 오라클 무료 서버(VM 인스턴스) 만들기
*(이미 오라클 무료 서버가 있다면 **STEP 2** 로 바로 넘어가세요)*

1. **오라클 클라우드 가입**: [Oracle Cloud Free Tier](https://www.oracle.com/kr/cloud/free/) 접속 후 무료 계정 가입 (본인 명의 해외결제 가능 신용/체크카드 필요, 약 $1 가승인 후 즉시 취소됨).
   - **홈 리전(Home Region)**: `South Korea Central (Seoul)` 또는 `Chuncheon` 선택.
2. **가상 서버(인스턴스) 생성**:
   - 좌측 상단 메뉴(☰) ➔ **컴퓨트(Compute)** ➔ **인스턴스(Instances)** ➔ **[인스턴스 생성(Create instance)]** 클릭
   - **이름**: `quant-ko-bot`
   - **이미지 및 구성(Image and shape)** 섹션에서 **[변경]** 클릭:
     - **이미지(OS)**: `Canonical Ubuntu` (22.04 또는 24.04 LTS) 선택
     - **구성(Shape)**: `VM.Standard.E2.1.Micro` (AMD 평생 무료) 또는 `VM.Standard.A1.Flex` (ARM 4코어/24GB 평생 무료) 선택 (**"항상 무료 적격(Always Free-eligible)"** 딱지 확인!)
   - **네트워킹(Networking)**: 기본값 유지 (`공용 IPv4 주소 지정` 체크 확인)
   - **SSH 키 추가(Add SSH keys)** (** 가장 중요!**):
     - **[자동으로 키 쌍 생성]** 선택 ➔ **[전용 키 저장(Save Private Key)]** 버튼을 눌러 `.key` 파일을 내 PC(예: `C:\Users\hakso\Downloads\ssh-key.key`)에 꼭 저장해 둡니다.
   - 하단 **[생성(Create)]** 클릭 ➔ 약 1\~2분 뒤 상태가 초록색 **실행 중(Running)** 으로 바뀌면 **공용 IP 주소(Public IP, 예: `152.xx.xx.xx`)** 를 메모합니다.

---

## STEP 2. 내 윈도우 PC에서 오라클 서버 접속하기

1. 윈도우에서 **PowerShell** 을 엽니다.
2. 아래 명령어에서 `키파일경로`와 `161.33.140.237`를 본인 것으로 바꿔 입력합니다.

```powershell
ssh -i "C:\Users\hakso\Downloads\ssh-key.key" ubuntu@161.33.140.237
```
- 처음 접속 시 `Are you sure you want to continue connecting (yes/no)?`가 나오면 `yes` 입력 후 엔터!
- 프롬프트가 `ubuntu@quant-ko-bot:\~$` 모양으로 바뀌면 오라클 서버 안으로 들어온 것입니다.

---

## STEP 3. 오라클 서버 기본 환경 세팅 (오라클 접속 창에 복붙)

서버에 접속된 상태(`ubuntu@...:\~$`)에서 아래 명령어들을 **한 블록씩 복사해서 붙여넣기** 합니다.

### 3-1. 한국 시간(KST) 설정 및 필수 프로그램 설치
```bash
sudo timedatectl set-timezone Asia/Seoul
date  # 현재 한국 시간이 맞는지 확인

sudo apt update && sudo apt install -y git python3-venv python3-pip
```

### 3-2. 깃허브에서 프로젝트 다운로드 및 설치
```bash
git clone https://github.com/haksoo0918/quant-ko.git
cd quant-ko
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e .
mkdir -p data
```

---

## STEP 4. 내 PC의 설정 파일(`.env`)과 DB(`quant_ko.db`) 서버로 보내기

비밀키가 담긴 `.env` 파일과 이미 수집해둔 10.5개년 데이터(`data/quant_ko.db`)는 깃허브에 올라가지 않으므로, **내 윈도우 PC에서 오라클 서버로 직접 복사** 해 줍니다.

1. 오라클 서버 창이 아닌, **내 윈도우 PC에서 새 PowerShell 창** 을 하나 더 엽니다.
2. 프로젝트 폴더로 이동한 뒤 `scp` 명령어로 파일 2개를 전송합니다:

```powershell
cd C:\Users\hakso\_work\quant-ko\www

# 1) .env 환경변수 파일 전송
scp -i "C:\Users\hakso\Downloads\ssh-key.key" .env ubuntu@161.33.140.237:\~/quant-ko/.env

# 2) SQLite 데이터베이스 파일 전송 (약 1\~2분 소요)
scp -i "C:\Users\hakso\Downloads\ssh-key.key" data/quant_ko.db ubuntu@161.33.140.237:\~/quant-ko/data/quant_ko.db
```

---

## STEP 5. 연동 확인 및 365일 무인 스케줄러(Crontab) 등록

다시 **오라클 서버 접속 창(`ubuntu@...`)** 으로 돌아옵니다.

### 5-1. 모의투자 계좌 조회가 잘 되는지 1회 테스트
```bash
cd \~/quant-ko
chmod 600 .env
.venv/bin/python -m quant_ko.main --mode status --env mock
```
- 화면에 **예수금, 총 평가액, 보유 종목(3종목)** 이 출력되고 디스코드 알림이 오면 세팅 100% 성공입니다!

### 5-2. 매일 자동으로 돌아가도록 크론탭(스케줄러) 등록
아래 명령어를 복사해서 오라클 서버 창에 그대로 붙여넣으면 평일 아침 감시와 15:20 리밸런싱이 자동 등록됩니다:

```bash
(crontab -l 2>/dev/null | grep -v "quant-ko"; cat << 'EOF'
# [quant-ko] 평일 08:30 관리종목/환기종목 일일 감시 (실행 전 git pull 자동 최신화)
30 8 * * 1-5 cd /home/ubuntu/quant-ko && git pull origin dev >> /home/ubuntu/quant-ko/deploy.log 2>&1 && /home/ubuntu/quant-ko/.venv/bin/python -m quant_ko.main --mode monitor --env mock >> /home/ubuntu/quant-ko/monitor.log 2>&1

# [quant-ko] 평일 15:20 월별 리밸런싱 장마감 시장가 자동 주문 (실행 전 git pull 자동 최신화, 모의투자 표준 모드)
20 15 * * 1-5 cd /home/ubuntu/quant-ko && git pull origin dev >> /home/ubuntu/quant-ko/deploy.log 2>&1 && /home/ubuntu/quant-ko/.venv/bin/python -m quant_ko.main --mode rebalance --env mock --strategy standard >> /home/ubuntu/quant-ko/rebalance.log 2>&1
EOF
) | crontab -
```

- **등록 확인**: `crontab -l` 입력 시 위 두 줄이 나오면 완료입니다!
- 이제 PC를 끄고 창을 닫아도 오라클 서버가 365일 알아서 감시하고 리밸런싱 후 디스코드로 상세 리포트를 보내줍니다.
