"""
홍익대학교 웹페이지 크롤링 코드 (최소 의존성 버전)
- 2번: 학사 공지사항 게시판 크롤링 (각 게시글 상세 페이지까지 들어가서 내용/첨부 처리)
- 3번: 산업·데이터공학과 개설과목 (JS 로딩 → API 엔드포인트를 알아야 해서 TODO로 처리)
- 4번: 산업·데이터공학과 학과 공지사항 크롤링 (각 게시글 상세 페이지까지)
"""

from unicodedata import name
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import json
import time
import urllib3
from urllib.parse import urljoin, urlparse, parse_qs
import PyPDF2
from io import BytesIO
import re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class HongikCrawler:
    DATE_PATTERN = re.compile(r"\d{4}\.\d{2}\.\d{2}")
    ATTACH_EXTS = (".pdf", ".hwp", ".hwpx", ".doc", ".docx",
                   ".xls", ".xlsx", ".ppt", ".pptx", ".zip")

    def __init__(self):
        self.session = requests.Session()
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko)"
            )
        }

    # ---------------- 공통 유틸 ---------------- #

    def _extract_date_from_row(self, tr):
        """tr 안의 td 텍스트 중 'YYYY.MM.DD' 형식을 찾아 datetime으로 반환"""
        for td in tr.find_all("td"):
            text = td.get_text(strip=True)
            m = self.DATE_PATTERN.search(text)
            if m:
                try:
                    return datetime.strptime(m.group(), "%Y.%m.%d")
                except ValueError:
                    return None
        return None

    def _extract_article_text(self, soup, title=None):
        """
        게시물 상세 페이지에서 타이틀/본문 텍스트 추출
        - title: 목록에서 가져온 제목(있으면 위치 기준으로 본문 구간 잘라냄)
        - 클래스명(.view_title 등)에 의존하지 않고 전체 텍스트에서 잘라내는 방식
        """
        full_text = soup.get_text("\n", strip=True)
        lines = [l.strip() for l in full_text.splitlines() if l.strip()]

        # 제목 위치 찾기 (목록에서 가져온 제목이 실제 페이지에도 동일하게 나타남)
        title_line = None
        idx_title = 0
        if title:
            for i, line in enumerate(lines):
                if line == title:
                    title_line = line
                    idx_title = i
                    break

        if not title_line:
            # 타이틀을 못 찾으면 첫 번째로 '공지사항' 아래 나오는 줄을 제목이라고 가정
            # (사이트마다 다를 수 있어서 완전 정확하진 않지만 최소 동작용)
            for i, line in enumerate(lines):
                if "공지사항" in line:
                    # 그 다음 non-empty line을 제목으로
                    for j in range(i + 1, len(lines)):
                        if lines[j]:
                            title_line = lines[j]
                            idx_title = j
                            break
                    break

        if not title_line:
            # 그래도 못 찾으면 그냥 첫 줄을 제목으로 처리
            title_line = lines[0] if lines else ""
            idx_title = 0

        # 본문 구간: [제목 다음 줄 ~ '이전글/다음글/목록' 전까지]
        body_lines = []
        for line in lines[idx_title + 1 :]:
            if line in ("이전글", "다음글", "목록"):
                break
            # 공유/프린터/메뉴 같은 메타 텍스트 제거
            if any(
                key in line
                for key in ("카카오 공유하기", "페이스북 공유하기", "URL 공유하기", "프린터")
            ):
                continue
            # '첨부파일' 문구 자체는 제외 (파일 리스트는 따로 처리)
            if "첨부파일" in line:
                continue
            body_lines.append(line)

        body_text = "\n".join(body_lines).strip()
        return title_line, body_text

    def _extract_attachments(self, soup, page_url):
        """
        상세 페이지에서 첨부파일 정보 추출
        - 이름과 URL, (PDF인 경우 내용 텍스트)까지
        - .pdf 외 확장자는 URL만 저장 (hwp 해석은 별도 라이브러리가 필요해서 여기선 제외)
        """
        attachments = []
        for a in soup.find_all("a"):
            name = a.get_text(strip=True)
            if not name:
                continue
            lower = name.lower()
            if not lower.endswith(self.ATTACH_EXTS):
                continue

            href = a.get("href")
            if not href or href.startswith("javascript"):
                continue

            file_url = urljoin(page_url, href)
            attach = {"name": name, "url": file_url, "content": None}

            # # PDF인 경우만 내용까지 추출 (PyPDF2 사용)
            # if lower.endswith(".pdf"):
            #     try:
            #         resp = self.session.get(file_url, headers=self.headers)
            #         if resp.ok:
            #             attach["content"] = self.extract_pdf_text(resp.content)
            #     except Exception:
            #         attach["content"] = "PDF 내용 추출 실패"

            attachments.append(attach)

        return attachments

    def extract_pdf_text(self, pdf_bytes):
        """PDF 파일에서 텍스트 추출"""
        try:
            pdf_file = BytesIO(pdf_bytes)
            reader = PyPDF2.PdfReader(pdf_file)
            text = ""
            for page in reader.pages:
                # PyPDF2의 extract_text는 버전에 따라 이름이 다를 수 있음
                text += page.extract_text() or ""
            return text.strip() or "PDF에 추출 가능한 텍스트가 없습니다."
        except Exception:
            return "PDF 내용 추출 실패"

    def _fetch_detail(self, post_url, title, post_date):
        try:
            resp = self.session.get(
                post_url,
                headers=self.headers,
                timeout=5
            )
            resp.raise_for_status()
        except Exception as e:
            print(f"[에러] 상세 페이지 요청 실패(HTTP): {post_url}, error={e}")
            return None

        try:
            detail_soup = BeautifulSoup(resp.text, "lxml")

            real_title, body = self._extract_article_text(detail_soup, title)
            attachments = self._extract_attachments(detail_soup, post_url)
        except Exception as e:
            print(f"[에러] 상세 페이지 파싱 실패: {post_url}, error={e}")
            real_title = title
            body = ""
            attachments = []

        if hasattr(post_date, "strftime"):
            date_str = post_date.strftime("%Y.%m.%d")
        else:
            date_str = str(post_date)

        return {
            "url": post_url,
            "title": real_title,
            "content": body,
            "date": date_str,
            "attachments": attachments,
        }



    # ---------------- 1. CN 홍익 로그인 ---------------- #

    def login_cn_hongik(self, user_id, password):
        """
        1번 링크 - CN 홍익 로그인
        ⚠️ 주의: 이 페이지는 실제로는 SSO/JS 기반일 가능성이 높음.
        → 반드시 브라우저 개발자도구(Network 탭)로 실제 로그인 요청 URL/파라미터를 확인해서
          아래 login_action_url / login_data를 수정해야 한다.
        """
        login_page = "https://cn.hongik.ac.kr/stud/"

        # 로그인 페이지 접속 (쿠키 세팅 용도)
        try:
            self.session.get(login_page, headers=self.headers, timeout=10)
        except Exception:
            return False

        # TODO: 개발자도구에서 실제 로그인 요청 URL/필드 확인 후 수정
        login_action_url = login_page  # 예시: "https://cn.hongik.ac.kr/stud/jsp/login/check_login.jsp"
        login_data = {
            "id": user_id,
            "pw": password,
            # 실제 필드명에 맞게 수정 필요
        }

        try:
            resp = self.session.post(
                login_action_url, data=login_data, headers=self.headers, timeout=10
            )
            return resp.ok
        except Exception:
            return False

    # ---------------- 2. 학사 공지사항 게시판 ---------------- #


    def _crawl_single_board(self, base_url, from_date, to_date=None):
        """
        - base_url부터 시작해서
        - b-paging-wrap 안의 '다음 페이지' 링크를 타고 계속 내려가면서
        - from_date ~ to_date 사이의 글들만 상세 크롤링해서 item을 yield
        """

        current_url = base_url
        visited = set()

        while True:
            # 0) 무한루프 방지
            if current_url in visited:
                print(f"[중단] 이미 방문한 URL 재방문 감지: {current_url}")
                break
            visited.add(current_url)

            # 1) 목록 페이지 요청
            try:
                resp = self.session.get(
                    current_url,
                    headers=self.headers,
                    timeout=5
                )
            except Exception as e:
                print(f"[에러] 목록 페이지 요청 실패: {current_url}, error={e}")
                break

            if not resp.ok:
                print(f"[에러] 목록 페이지 status={resp.status_code}: {current_url}")
                break

            # 2) 파싱
            soup = BeautifulSoup(resp.text, "lxml")
            rows = soup.select("tbody tr") or soup.select("tr")

            page_has_not_too_old_post = False   # from_date 이상 글이 있었는지
            tasks = []                          # (post_url, title, post_date, post_no)

            for tr in rows:
                link_elem = tr.find("a")
                if not link_elem:
                    continue

                # 게시글 번호 (있으면)
                num_td = tr.find("td", class_="b-num-box")
                post_no = None
                if num_td:
                    try:
                        post_no = int(num_td.get_text(strip=True))
                    except ValueError:
                        post_no = None

                # 날짜 추출
                post_date = self._extract_date_from_row(tr)
                if not post_date:
                    continue

                # post_date 타입 통일 (datetime → date, str이면 파싱)
                if isinstance(post_date, datetime):
                    post_date = post_date.date()
                elif isinstance(post_date, str):
                    # 예: "2025.11.29" 형태라면
                    try:
                        post_date = datetime.strptime(post_date, "%Y.%m.%d").date()
                    except ValueError:
                        # 형식이 다르면 그냥 건너뛴다
                        continue

                # ① from_date보다 옛날이면: 이번 범위에서는 필요 없음
                if post_date < from_date:
                    # 이 글은 너무 오래된 글 → 이번 범위에서는 스킵
                    continue

                # 여기까지 왔으면 적어도 from_date 이상인 글이라는 뜻
                page_has_not_too_old_post = True

                # ② to_date가 있고, 그보다 더 "최근"이면: 이번 범위가 아니라 더 최신범위에서 다룰 대상
                if to_date is not None and post_date > to_date:
                    continue

                # ③ 실제 수집 대상 (from_date ~ to_date 사이)
                title = link_elem.get_text(strip=True)
                href = link_elem.get("href")
                if not href:
                    continue

                post_url = urljoin(current_url, href)
                tasks.append((post_url, title, post_date, post_no))

            # 디버깅용: 이 페이지 요약
            print(
                f"[목록] url={current_url}, rows={len(rows)}, "
                f"from_date이상존재={page_has_not_too_old_post}, "
                f"수집대상글수={len(tasks)}"
            )

            # 3) 이 페이지에 from_date 이상인 글이 하나도 없으면
            #    아래 페이지는 전부 더 옛날 글 → 더 볼 필요 없음
            if not page_has_not_too_old_post:
                print(f"[중단] {current_url} 이후로는 {from_date} 이전 글만 있음 → 종료")
                break

            # 4) 상세 페이지 병렬 요청
            if tasks:
                max_workers = getattr(self, "max_workers", 5)

                with ThreadPoolExecutor(max_workers=max_workers) as ex:
                    futures = [
                        ex.submit(self._fetch_detail, post_url, title, post_date)
                        for (post_url, title, post_date, post_no) in tasks
                    ]

                    for (future, (post_url, title, post_date, post_no)) in zip(futures, tasks):
                        try:
                            item = future.result()
                        except Exception as e:
                            print(f"[에러] 상세 크롤링 실패: {post_url}, error={e}")
                            continue

                        if item is None:
                            continue

                        item["post_no"] = post_no
                        # board_base_url은 바깥에서 붙이니까 여기선 안 건드림
                        yield item

            # 5) 다음 페이지 이동
            time.sleep(0.1)  # 서버 예의상 잠깐 쉼

            paging_wrap = soup.find("div", class_="b-paging-wrap")
            if not paging_wrap:
                print("[중단] b-paging-wrap 없음 → 마지막 페이지로 판단")
                break

            next_a = paging_wrap.select_one("li.next.pager > a")
            if not next_a:
                print("[중단] li.next.pager a 없음 → 다음 페이지 없음")
                break

            href = next_a.get("href")
            if not href or href.startswith("javascript"):
                print(f"[중단] next 링크 이상함: href={href}")
                break

            next_url = urljoin(base_url, href)
            if next_url in visited:
                print(f"[중단] 다음 URL이 이미 방문한 URL: {next_url}")
                break

            print(f"다음 페이지 이동: {next_url}")
            current_url = next_url



    def crawl_academic_board(
        self,
        save_path="academic_board.jsonl",
        chunk_size=100,
        days_per_step=100,   # ★ 100일 단위
        total_days=730,      # ★ 전체는 2년치 정도
    ):
        from datetime import datetime, timedelta
        from pathlib import Path
        import json

        board_urls = [
            "https://www.hongik.ac.kr/kr/newscenter/notice.do",
        ]

        save_path = Path(save_path)

        # === chunk 상태 ===
        current_chunk_idx = 0
        current_items = []
        current_min_date = None
        current_max_date = None

        def flush_current_chunk():
            nonlocal current_chunk_idx, current_items, current_min_date, current_max_date

            if not current_items:
                return

            if current_min_date is None or current_max_date is None:
                chunk_label = f"idx={current_chunk_idx}"
                min_date_str = None
                max_date_str = None
            else:
                chunk_label = f"{current_max_date:%Y.%m.%d}~{current_min_date:%Y.%m.%d}"
                min_date_str = current_min_date.isoformat()
                max_date_str = current_max_date.isoformat()

            record = {
                "chunk_meta": {
                    "idx": current_chunk_idx,
                    "label": chunk_label,
                    "count": len(current_items),
                    "min_date": min_date_str,
                    "max_date": max_date_str,
                },
                "items": current_items,
            }

            with save_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

            print(
                f"[저장] idx={current_chunk_idx}, "
                f"기간={chunk_label}, 개수={len(current_items)} → {save_path}"
            )

            current_items = []
            current_min_date = None
            current_max_date = None
            current_chunk_idx += 1

        # === 날짜 범위를 100일씩 자르기 ===
        today = datetime.now().date()
        oldest = today - timedelta(days=total_days)

        # ex) [오늘-0~99], [100~199], ... 이런 식으로 뒤로 내려가면서
        date_ranges = []
        cur_end = today
        while cur_end > oldest:
            cur_start = max(oldest, cur_end - timedelta(days=days_per_step - 1))
            # 겹치지 않게 하기 위해 다음 구간 end = start - 1
            date_ranges.append((cur_start, cur_end))
            cur_end = cur_start - timedelta(days=1)

        # 최신 구간부터 돌고 싶으면 그냥 그대로 사용
        # 오래된 것부터 돌고 싶으면 date_ranges.reverse()

        for (from_date, to_date) in date_ranges:
            print(f"\n[범위 시작] {from_date} ~ {to_date}")

            for base_url in board_urls:
                print(f"[시작] {base_url} / {from_date}~{to_date}")

                for item in self._crawl_single_board(base_url, from_date, to_date):
                    item["board_base_url"] = base_url

                    post_date = datetime.strptime(item["date"], "%Y.%m.%d").date()
                    if current_min_date is None or post_date < current_min_date:
                        current_min_date = post_date
                    if current_max_date is None or post_date > current_max_date:
                        current_max_date = post_date

                    current_items.append(item)

                    if len(current_items) >= chunk_size:
                        flush_current_chunk()

                print(f"[완료] {base_url} / {from_date}~{to_date}")

        flush_current_chunk()
        print("[전체 완료]")



    # ---------------- 3. 산업·데이터공학과 개설과목 ---------------- #

    def crawl_ie_courses(self):
        url = "https://ie.hongik.ac.kr/ie/0301.do"

        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")

        driver = webdriver.Chrome(options=options)
        driver.get(url)

        try:
            ul_grid = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "ul.grid"))
            )

            boxes = ul_grid.find_elements(By.CSS_SELECTOR, "div.curriculum-title-box")

            courses = []
            for idx, box in enumerate(boxes, start=1):
                # 🔹 HTML 태그 X, 텍스트만 사용
                text = box.text.strip()

                courses.append({
                    "index": idx,
                    "text": text
                })

            return courses

        finally:
            driver.quit()



    # ---------------- 4. 산업·데이터공학과 학과 공지사항 ---------------- #

    def crawl_ie_board(self):
        """
        산업데이터공학과(및 동일 템플릿 학과)의 학과 공지사항 크롤링
        - board_urls 리스트의 각 URL을 1페이지부터 시작
        - 각 URL(학부/학과)마다:
          1) 1페이지부터 시작
          2) 각 페이지에서 최근 6개월 이내 글만 상세 페이지까지 크롤링
          3) 해당 페이지에 최근 6개월 이내 글이 하나도 없으면 -> 그 학부 크롤링 종료
          4) div.b-paging 안에서 (현재페이지+1) 텍스트를 가진 a 태그를 찾아 다음 페이지로 이동
        """

        # ✅ 여기서 name, url을 같이 관리
        boards = [
            {"name": "산업데이터공학과", "url": "https://ie.hongik.ac.kr/ie/0401.do"},
            
            # 공과대학_(신소재공학전공 링크 접근 불가, 기초과학과 글 없음)
            {"name": "전기전자공학부", "url": "https://ee.hongik.ac.kr/ee/0501.do"},
            {"name": "화학공학전공", "url": "https://chemeng.hongik.ac.kr/chemeng/sub/0401.do"},
            {"name": "컴퓨터공학과", "url": "https://wwwce.hongik.ac.kr/wwwce/0401.do"},
            {"name": "기계시스템디자인공학과", "url": "https://me.hongik.ac.kr/me/0701.do"},
            {"name": "건설환경공학과", "url": "https://civil.hongik.ac.kr/civil/0401.do"},

            # 경영대학
            {"name": "경영대학", "url": "https://bizadmin.hongik.ac.kr/bizadmin/0401.do"},

            # 법과대학
            {"name": "법과대학", "url": "https://law.hongik.ac.kr/law/0401.do"},

            # 미술대학_(시각디자인/금속조형디자인 다른 형식의 홈페이지)
            {"name": "동양화과", "url": "https://orip.hongik.ac.kr/orip/0401.do"},
            {"name": "회화과", "url": "https://painting.hongik.ac.kr/painting/0401.do"},
            {"name": "판화과", "url": "https://printmk.hongik.ac.kr/printmk/0401.do"},
            {"name": "조소과", "url": "https://scu.hongik.ac.kr/scu/0401.do"},
            {"name": "산업디자인전공", "url": "https://id.hongik.ac.kr/id/0401.do"},
            {"name": "도예유리과", "url": "https://cer.hongik.ac.kr/cer/0401.do"},
            {"name": "목조형가구학과", "url": "https://waf.hongik.ac.kr/waf/0401.do"},
            {"name": "예술학과", "url": "https://art.hongik.ac.kr/art/0401.do"},

            # 디자인예술경영학부
            {"name": "디자인예술경영학부", "url": "https://iim.hongik.ac.kr/iim/0401.do"},

            # 캠퍼스자율전공(서울)
            {"name": "캠퍼스자율전공", "url": "https://fm.hongik.ac.kr/fm/0401.do"},

            # 바이오헬스융합학부
            {"name": "바이오헬스융합학부", "url": "https://biocoss.hongik.ac.kr/biocoss/0401.do"},

            # 과학기술대학
            {"name": "과학기술대학", "url": "https://cst.hongik.ac.kr/cst/0501.do"},

            # 건축도시대학_(건축공학/도시공학과 패스 다른 형식의 홈페이지)

            # # 문과대학
            {"name": "영여영문학과", "url": "https://english.hongik.ac.kr/english/0401.do"},
            {"name": "독어독문학과", "url": "https://german.hongik.ac.kr/german/0401.do"},
            {"name": "불어불문학과", "url": "https://france.hongik.ac.kr/france/0401.do"},
            {"name": "국어국문학과", "url": "https://hkorean.hongik.ac.kr/hkorean/0401.do"},

            # 사범대학
            {"name": "수학교육과", "url": "https://math.hongik.ac.kr/math/0401.do"},
            {"name": "국어교육과", "url": "https://koredu.hongik.ac.kr/koredu/0401.do"},
            {"name": "영어교육과", "url": "https://educomplex.hongik.ac.kr/educomplex/0401.do"},
            {"name": "역사교육과", "url": "https://hisedu.hongik.ac.kr/hisedu/0401.do"},
            {"name": "교육학과", "url": "https://edu.hongik.ac.kr/edu/0401.do"},

            # 경제학부
            {"name": "경제학부", "url": "https://economics.hongik.ac.kr/economics/0401.do"},

            # # 공연예술학부
            {"name": "뮤지컬전공", "url": "https://musical.hongik.ac.kr/musical/0501.do"},
            {"name": "실용음악전공", "url": "https://music.hongik.ac.kr/music/0501.do"},

            # 융합전공 
            # 아래는 홈페이지 없는 학과들
            # 공연예술전공/건축공간예술전공/사물인터넷공학/지능로봇공학/스마트도시데이터사이언스
            # 데이터사이언스/의료헬스케어AI/헬스케어서비스전공
            {"name": "문화예술경영학과", "url": "https://hicam.hongik.ac.kr/hicam/0401.do"},
            {"name": "디자인엔지니어링전공", "url": "https://smpd.hongik.ac.kr/smpd/0401.do"},
            
        ]

        # six_months_ago = datetime.now() - timedelta(days=180)  # 실제 운영
        six_months_ago = datetime.now() - timedelta(days=730)      # 2년치로 운영조정

        results_by_board = {}

        for board in boards:
            name = board["name"]      # 딕셔너리 key로 쓸 이름
            base_url = board["url"]   # 크롤링에 사용할 URL

            print(f"학과 {name} 크롤링 시작...")
            board_results = self._crawl_single_ie_board(base_url, six_months_ago)

            # ✅ 여기서 URL이 아니라 name을 key로 사용
            results_by_board[name] = board_results

            # ✅ 크롤링 진행상황 출력 (원하는 멘트로 수정 가능)
            print(f"[크롤링 완료] {name} ({base_url}) - {len(board_results)}건 수집")

        return results_by_board



    def _crawl_single_ie_board(self, base_url, six_months_ago):
        """
        하나의 산업데이터공학과(또는 동일 템플릿 학과) 공지 게시판에 대해
        '최근 6개월 이내 글만' 페이지를 넘기며 크롤링하는 공통 로직
        """

        results = []
        current_page = 1
        current_url = base_url
        visited = set()

        while True:
            # 혹시 중복 요청 방지
            if current_url in visited:
                break
            visited.add(current_url)

            # --- 현재 페이지 요청 --- #
            try:
                resp = self.session.get(
                    current_url,
                    headers=self.headers,
                    timeout=10,
                    verify=False,   # 🔹 SSL 인증서 검증 끔
                )
            except requests.exceptions.SSLError as e:
                print(f"[경고] 학과 공지 요청 중 SSL 에러 발생, ie_board 크롤링을 건너뜁니다: {e}")
                break

            if not resp.ok:
                break

            soup = BeautifulSoup(resp.text, "html.parser")

            # 게시물 목록 tr
            posts = soup.select("tbody tr") or soup.select("tr")

            # 이 페이지에 '최근 6개월 이내 글'이 있었는지
            page_has_recent_post = False

            for post in posts:
                # 제목 a 태그 없으면 스킵 (헤더/빈 행 등)
                link_elem = post.find("a")
                if not link_elem:
                    continue

                # 공지(상단 고정) 제외하고 싶으면: 첫 번째 td가 '공지'면 스킵
                # tds = post.find_all("td")
                # if tds and tds[0].get_text(strip=True) == "공지":
                #     continue

                post_date = None
                tds = post.find_all("td")

                for td in tds:
                    text = td.get_text(strip=True)
                    # YYYY.MM.DD 형태인지 검사
                    if re.fullmatch(r"\d{4}\.\d{2}\.\d{2}", text):
                        try:
                            post_date = datetime.strptime(text, "%Y.%m.%d")
                        except ValueError:
                            post_date = None
                        break

                # 날짜를 찾지 못하면 스킵
                if not post_date:
                    continue

                # 6개월 이내 글인지 확인
                if post_date >= six_months_ago:
                    page_has_recent_post = True
                else:
                    # 이 글은 너무 오래된 글이라 상세 크롤링 안 함
                    continue

                title = link_elem.get_text(strip=True)
                href = link_elem.get("href")
                if not href:
                    continue

                post_url = urljoin(current_url, href)

                # --- 개별 게시글 상세 페이지 요청 --- #
                try:
                    detail_resp = self.session.get(post_url, headers=self.headers)
                    if not detail_resp.ok:
                        continue
                except Exception:
                    continue

                detail_soup = BeautifulSoup(detail_resp.text, "html.parser")

                # 상세 내용 추출 (기존 방식 그대로 유지)
                content = {
                    "url": post_url,
                    "title": "",
                    "content": "",
                    "date": post_date.strftime("%Y.%m.%d"),
                    "attachments": [],
                }

                # 제목 및 본문
                title_elem = detail_soup.select_one(".view_title") or detail_soup.find("h4")
                if title_elem:
                    content["title"] = title_elem.get_text(strip=True)
                else:
                    content["title"] = title

                body_elem = detail_soup.select_one(".view_content") or detail_soup.find("div", class_="view_con")
                if body_elem:
                    content["content"] = body_elem.get_text(strip=True)
                else:
                    # fallback: 페이지 전체에서 본문 후보 영역을 못 찾으면 그냥 전체 텍스트 일부
                    content["content"] = detail_soup.get_text(separator="\n", strip=True)

                # 첨부파일 처리
                attachments = detail_soup.select(".file_download a")
                for attachment in attachments:
                    file_url = urljoin(post_url, attachment.get("href", ""))
                    file_name = attachment.get_text(strip=True)

                    file_info = {"name": file_name, "content": None}

                    # # PDF면 내용 추출 시도
                    # if file_name.lower().endswith(".pdf"):
                    #     try:
                    #         file_resp = self.session.get(file_url, headers=self.headers)
                    #         if file_resp.ok:
                    #             pdf_text = self.extract_pdf_text(file_resp.content)
                    #             file_info["content"] = pdf_text
                    #     except Exception:
                    #         file_info["content"] = "PDF 내용 추출 실패"

                    # content["attachments"].append(file_info)

                results.append(content)
                time.sleep(0.2)

            # ✅ 이 페이지에 최근 6개월 이내 글이 하나도 없으면 더 이상 내려갈 필요 없음
            if not page_has_recent_post:
                break

            # --- 다음 페이지: (현재페이지 + 1) 텍스트를 가진 a 태그 찾기 --- #
            paging_div = soup.find("div", class_="b-paging")
            if not paging_div:
                break

            next_page_num = current_page + 1
            next_link_tag = None

            for a in paging_div.find_all("a"):
                text = a.get_text(strip=True)
                if text == str(next_page_num):  # "2", "3", ...
                    next_link_tag = a
                    break

            # 다음 페이지 번호가 없으면 종료
            if not next_link_tag:
                break

            href = next_link_tag.get("href")
            if not href or href.startswith("javascript"):
                break

            # 다음 페이지로 이동
            current_url = urljoin(base_url, href)
            current_page = next_page_num
            time.sleep(0.2)

        return results



    # ---------------- 결과 저장 & 실행 ---------------- #

    def save_results(self, data, filename):
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def run(self, user_id=None, password=None):
        print("크롤링 시작...")

        all_results = {}

        # 1. CN 홍익 로그인 (필요할 때만)
        if user_id and password:
            print("1. CN 홍익 로그인 시도...")
            if self.login_cn_hongik(user_id, password):
                print("   로그인 성공")
            else:
                print("   로그인 실패 (login_cn_hongik 내용 수정 필요)")

        # 2. 학사 공지사항
        # print("2. 학사 공지사항 크롤링...")
        # academic_data = self.crawl_academic_board() or []   # ✅ None이면 빈 리스트로 대체
        # all_results['academic_board'] = academic_data
        # print(f"   {len(academic_data)}개 게시물 크롤링 완료")

        # 3. 산업·데이터공학과 개설과목
        print("3. 개설과목 크롤링...")
        courses_data = self.crawl_ie_courses()
        all_results['ie_courses'] = courses_data
        print(f"   {len(courses_data)}개 과목 크롤링 완료")

        # 4. 산업·데이터공학과 학과 공지사항
        print("4. 학과 공지사항 크롤링...")
        ie_board_data = self.crawl_ie_board()
        all_results["ie_board"] = ie_board_data
        print(f"   {len(ie_board_data)}개 게시물 크롤링 완료")

        # 결과 저장
        self.save_results(all_results, "hongik_crawled_data.json")
        print("\n크롤링 완료! 결과가 'hongik_crawled_data.json'에 저장되었습니다.")

        return all_results


if __name__ == "__main__":
    crawler = HongikCrawler()
    courses = crawler.crawl_ie_courses()
    print(len(courses))
    print(courses[:3])

    # ⚠️ 중요한 보안 주의:
    #   실제 코드에는 학번/비밀번호를 하드코딩하지 말고
    #   환경변수나 별도 설정 파일에서 읽어오는 방식으로 처리하는 걸 추천.
    #
    # 예시:
    # import os
    # user = os.environ.get("HONGIK_ID")
    # pw = os.environ.get("HONGIK_PW")
    # results = crawler.run(user_id=user, password=pw)

    # 로그인 없이 공개 페이지만 크롤링:
    results = crawler.run()
