# Stash — iPhone 공유 시트 → Mac Obsidian LLM 위키

인스타그램 릴스(또는 아무 링크/텍스트) → 공유 → **Stash** 한 번 탭 → Mac의 Obsidian 볼트 `raw/`에 저장 →
(옵션) `claude -p`가 `wiki/`로 정리.

```
iPhone Share Extension ──HTTP(Tailscale/Wi-Fi)──▶ Mac server/stash_server.py
                                                    ├─ raw/<날짜>-<slug>.md   즉시 저장 (status: raw)
                                                    ├─ yt-dlp / OpenGraph     메타데이터 보강 (status: enriched)
                                                    └─ claude -p (--compile)  wiki/ 페이지·index·log 갱신 (status: compiled)
```

## 구성
| 경로 | 역할 |
|---|---|
| `server/stash_server.py` | Mac 수신 서버 (Python 3.9 표준 라이브러리만) |
| `server/vault_template/` | 첫 실행 때 볼트에 채워지는 구조 (CLAUDE.md 규칙, Home, Inbox.base, wiki/) |
| `server/run.sh` | 토큰 생성 + 주소 출력 + 서버 실행 |
| `server/install-launchagent.sh` | 로그인 시 자동 실행 등록 (선택) |
| `ios/CaptureKit` | 앱·확장이 공유하는 Swift 패키지 (추출·전송·설정) |
| `ios/StashShare` | Share Extension — 탭하면 바로 전송, 성공 시 자동 닫힘 |
| `ios/Stash` | 설정 앱 (Mac 주소·토큰·연결 테스트) |
| `ios/project.yml` | XcodeGen 정의 → `Stash.xcodeproj` |

## 설치
1. **Mac 서버**
   ```bash
   ./server/run.sh            # 기본 볼트: iCloud Obsidian/Sihoon Archive
   ```
   출력된 주소(Tailscale `100.x.x.x:8765` 권장)와 토큰을 메모. 상시 실행은 `./server/install-launchagent.sh "<볼트 경로>" --compile`.
2. **Obsidian**: 위 볼트 폴더를 "Open folder as vault".
3. **iPhone 앱** (Xcode 필요)
   ```bash
   cd ios && xcodegen generate && open Stash.xcodeproj
   ```
   Signing & Capabilities에서 Team 선택(두 타깃 모두) → iPhone 연결 → Run.
   앱에서 주소·토큰 입력 → "연결 테스트" ✅.
4. 인스타그램 릴스 → 공유 → `⋯ 더 보기`에서 Stash를 즐겨찾기 맨 앞으로 올려두면 한 번 탭으로 저장.

### 인스타그램 캡션 가져오기 (선택)
인스타그램은 비로그인 조회를 막아서 기본값으로는 URL과 공유 텍스트만 저장됩니다. 캡션·작성자까지 받으려면:
```bash
STASH_YTDLP_ARGS="--cookies-from-browser chrome" ./server/run.sh --vault ... --compile
```

## 테스트
```bash
./test.sh
```
- Python: 입력 검증, 인증, 파일명 충돌, 보강 워커, 컴파일 프롬프트 전달 (11개)
- Swift `CaptureKit`: 공유 항목 추출, 설정, 그리고 **E2E** — 인스타그램식 `NSItemProvider` → 추출기 → `ReceiverClient` → 실제 Python 서버 → 볼트 파일 검증 (8개)

## 앞으로 확장할 곳
- 이미지/스크린샷/PDF: `NSExtensionActivationRule`에 이미지 지원 추가 + `/capture`에 multipart 업로드
- 릴스 음성 → 텍스트: 워커에서 `yt-dlp -x` + whisper로 전사 후 노트에 첨부
- Mac이 꺼져 있을 때: 확장에서 실패한 캡처를 App Group에 쌓아두고 앱이 재전송
