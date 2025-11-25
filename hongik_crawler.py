"""
홍익대학교 웹페이지 크롤링 코드 (최소 의존성 버전)
- 2번: 학사 공지사항 게시판 크롤링 (각 게시글 상세 페이지까지 들어가서 내용/첨부 처리)
- 3번: 산업·데이터공학과 개설과목 (JS 로딩 → API 엔드포인트를 알아야 해서 TODO로 처리)
- 4번: 산업·데이터공학과 학과 공지사항 크롤링 (각 게시글 상세 페이지까지)
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import json
import time
from urllib.parse import urljoin, urlparse, parse_qs
import PyPDF2
from io import BytesIO
import re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC



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

            # PDF인 경우만 내용까지 추출 (PyPDF2 사용)
            if lower.endswith(".pdf"):
                try:
                    resp = self.session.get(file_url, headers=self.headers)
                    if resp.ok:
                        attach["content"] = self.extract_pdf_text(resp.content)
                except Exception:
                    attach["content"] = "PDF 내용 추출 실패"

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

    def crawl_academic_board(self):
        """
        학사 공지사항(뉴스센터 공지) 크롤링
        - 시작: https://www.hongik.ac.kr/kr/newscenter/notice.do (1페이지라고 가정)
        - 동작:
          1) 현재 페이지의 모든 글을 돌면서
             - 작성일이 최근 6개월 이내인 글만 상세페이지까지 크롤링
          2) 그 페이지에 '최근 6개월 이내 글'이 하나도 없으면 -> 여기서 전체 크롤링 종료
          3) 그렇지 않으면 b-paging 안에서 (현재페이지+1) 텍스트를 가진 a 태그를 찾아
             다음 페이지로 이동하고 1번부터 반복
        """
        base_url = "https://www.hongik.ac.kr/kr/newscenter/notice.do"
        # six_months_ago = datetime.now() - timedelta(days=180) # 오래걸리니 test시에는 3만 해서 돌릴것
        six_months_ago = datetime.now() - timedelta(days=20)

        results = []
        current_page = 1
        current_url = base_url
        visited = set()

        while True:
            if current_url in visited:
                # 혹시나 루프 도는 상황 방지
                break
            visited.add(current_url)

            # --- 현재 페이지 요청 --- #
            resp = self.session.get(current_url, headers=self.headers)
            if not resp.ok:
                break

            soup = BeautifulSoup(resp.text, "html.parser")

            rows = soup.select("tbody tr") or soup.select("tr")

            # 이 페이지에서 '최근 6개월 이내 글'이 있었는지 표시
            page_has_recent_post = False

            for tr in rows:
                link_elem = tr.find("a")
                if not link_elem:
                    continue

                # 작성일 추출
                post_date = self._extract_date_from_row(tr)
                if not post_date:
                    continue

                # 6개월 이내인지 체크
                if post_date >= six_months_ago:
                    page_has_recent_post = True
                else:
                    # 이 글은 너무 오래된 글이라서 크롤링에서 제외
                    continue

                title = link_elem.get_text(strip=True)
                href = link_elem.get("href")
                if not href:
                    continue

                post_url = urljoin(current_url, href)

                # --- 상세 페이지 요청 --- #
                detail_resp = self.session.get(post_url, headers=self.headers)
                if not detail_resp.ok:
                    continue

                detail_soup = BeautifulSoup(detail_resp.text, "html.parser")

                real_title, body = self._extract_article_text(detail_soup, title)
                attachments = self._extract_attachments(detail_soup, post_url)

                results.append({
                    "url": post_url,
                    "title": real_title,
                    "content": body,
                    "date": post_date.strftime("%Y.%m.%d"),
                    "attachments": attachments
                })

                time.sleep(0.2)

            # ✅ 이 페이지에 최근 6개월 이내 글이 하나도 없으면,
            #   이 이후 페이지들도 더 오래된 글일 가능성이 크므로 여기서 종료
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
                if text == str(next_page_num):   # "2", "3", ...
                    next_link_tag = a
                    break

            # 다음 페이지 번호 링크가 없으면 종료
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
        4번 링크 - 산업데이터공학과 학과 공지사항 크롤링
        - URL: https://ie.hongik.ac.kr/ie/0401.do
        - 동작:
          1) 1페이지부터 시작
          2) 각 페이지에서 최근 6개월 이내 글만 상세 페이지까지 크롤링
          3) 해당 페이지에 최근 6개월 이내 글이 하나도 없으면 -> 전체 크롤링 종료
          4) div.b-paging 안에서 (현재페이지+1) 텍스트를 가진 a 태그를 찾아 다음 페이지로 이동
        """
        base_url = "https://ie.hongik.ac.kr/ie/0401.do"
        # six_months_ago = datetime.now() - timedelta(days=180)
        six_months_ago = datetime.now() - timedelta(days=20)

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
                tds = post.find_all("td")
                if tds and tds[0].get_text(strip=True) == "공지":
                    continue

                # 날짜 컬럼: 기존 코드처럼 3번째 td 기준
                date_elem = post.select_one("td:nth-child(3)")
                post_date = None
                if date_elem:
                    try:
                        post_date = datetime.strptime(
                            date_elem.get_text(strip=True), "%Y.%m.%d"
                        )
                    except Exception:
                        post_date = None

                # 날짜 없으면 스킵
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

                # 제목 및 본문 (페이지 구조에 맞게 조정 가능)
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

                # 첨부파일 처리 (기존 코드 스타일 유지)
                attachments = detail_soup.select(".file_download a")
                for attachment in attachments:
                    file_url = urljoin(post_url, attachment.get("href", ""))
                    file_name = attachment.get_text(strip=True)

                    file_info = {"name": file_name, "content": None}

                    # PDF면 내용 추출 시도
                    if file_name.lower().endswith(".pdf"):
                        try:
                            file_resp = self.session.get(file_url, headers=self.headers)
                            if file_resp.ok:
                                pdf_text = self.extract_pdf_text(file_resp.content)
                                file_info["content"] = pdf_text
                        except Exception:
                            file_info["content"] = "PDF 내용 추출 실패"

                    content["attachments"].append(file_info)

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
        print("2. 학사 공지사항 크롤링...")
        academic_data = self.crawl_academic_board() or []   # ✅ None이면 빈 리스트로 대체
        all_results['academic_board'] = academic_data
        print(f"   {len(academic_data)}개 게시물 크롤링 완료")

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
