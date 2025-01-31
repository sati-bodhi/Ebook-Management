from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Generator, Iterable, Optional, List, ContextManager, Dict, Tuple
from urllib.parse import unquote
import uuid
from itertools import chain, count
import re
import json
from math import ceil

from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver import Firefox
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


@dataclass
class Result:
    title: str  # Mozi's Theory of Human Nature and Politics
    title_link: str  # http://big5.oversea.cnki.net/kns55/detail/detail.aspx?recid=&FileName=ZDXB202006009&DbName=CJFDLAST2021&DbCode=CJFD
    html_link: Optional[str]  # http%3a%2f%2fkns.cnki.net%2fKXReader%2fDetail%3fdbcode%3dCJFD%26filename%3dZDXB202006009
    author: str  # Xie Qiyang
    source: str  # Vocational University News
    source_link: str  # http://big5.oversea.cnki.net/kns55/Navi/ScdbBridge.aspx?DBCode=CJFD&BaseID=ZDXB&UnitCode=&NaviLink=%e8%81%8c%e5%a4%a7%e5%ad%a6%e6%8a%a5
    date: date  # 2020-12-28
    download: str  #
    database: str  # Periodical

    @classmethod
    def from_row(cls, row: WebElement) -> 'Result':
        number, title, author, source, published, database = row.find_elements_by_xpath('td')

        title_links = title.find_elements_by_tag_name('a')

        if len(title_links) > 1:
            # 'http://big5.oversea.cnki.net/kns55/ReadRedirectPage.aspx?flag=html&domain=http%3a%2f%2fkns.cnki.net%2fKXReader%2fDetail%3fdbcode%3dCJFD%26filename%3dZDXB202006009'
            html_link = unquote(
                title_links[1]
                    .get_attribute('href')
                    .split('domain=', 1)[1])
        else:
            html_link = None

        dl_links, sno = number.find_elements_by_tag_name('a')
        dl_links = dl_links.get_attribute('href')

        if re.search("javascript:alert.+", dl_links):
            dl_links = None

        published_date = date.fromisoformat(
            published.text.split(maxsplit=1)[0]
        )

        return cls(
            title=title_links[0].text,
            title_link=title_links[0].get_attribute('href'),
            html_link=html_link,
            author=author.text,
            source=source.text,
            source_link=source.get_attribute('href'),
            date=published_date,
            download=dl_links,
            database=database.text,
        )

    def __str__(self):
        return (
            f'題名      {self.title}'
            f'\n作者     {self.author}'
            f'\n來源     {self.source}'
            f'\n發表時間  {self.date}'
            f'\n下載連結　{self.download}'
            f'\n來源數據庫 {self.database}'
        )

    def as_dict(self) -> Dict[str, str]:
        return {
            'author': self.author,
            'title': self.title,
            'publication/university': self.source,
            'date': self.date.isoformat(),
            'download': self.download,
            'url': self.html_link,
            'database': self.database,
        }

    def as_bib(self) -> Dict[str, str]:
        id = uuid.uuid1()
        if self.database == "期刊" or self.database == "輯刊":
            return {
                'ID': str(id.hex),
                'ENTRYTYPE': 'article',
                'author': self.author,
                'title': self.title,
                'journaltitle': self.source,
                'date': self.date.isoformat(),
                'url': self.html_link,
                # 'file': self.download,
            }
        elif self.database == "博士":
            return {
                'ID': str(id.hex),
                'ENTRYTYPE': 'phdthesis',
                'author': self.author,
                'title': self.title,
                'institution': self.source,
                'date': self.date.isoformat(),
                'url': self.download,
                # 'file': self.download,
            }
        elif self.database == "碩士":
            return {
                'ID': str(id.hex),
                'ENTRYTYPE': 'mastersthesis',
                'author': self.author,
                'title': self.title,
                'institution': self.source,
                'date': self.date.isoformat(),
                'url': self.download,
                # 'file': self.download,
            }

class MainPage:
    def __init__(self, driver: WebDriver):
        self.driver = driver

    def submit_search(self, keyword: str) -> None:
        wait = WebDriverWait(self.driver, 50)
        search = wait.until(
            EC.presence_of_element_located((By.NAME, 'txt_1_value1'))
        )
        search.send_keys(keyword)
        search.submit()

    def switch_to_frame(self) -> None:
        wait = WebDriverWait(self.driver, 100)
        wait.until(
            EC.presence_of_element_located((By.XPATH, '//iframe[@name="iframeResult"]'))
        )
        self.driver.switch_to.default_content()
        self.driver.switch_to.frame('iframeResult')

        wait.until(
            EC.presence_of_element_located((By.XPATH, '//table[@class="GridTableContent"]'))
        )

    def max_content(self) -> None:
        """Maximize the number of items on display in the search results."""
        max_content = self.driver.find_element(
            By.CSS_SELECTOR, '#id_grid_display_num > a:nth-child(3)',
        )
        max_content.click()

    # def get_element_and_stop_page(self, *locator) -> WebElement:
    #     ignored_exceptions = (NoSuchElementException, StaleElementReferenceException)
    #     wait = WebDriverWait(self.driver, 30, ignored_exceptions=ignored_exceptions)
    #     elm = wait.until(EC.presence_of_element_located(locator))
    #     self.driver.execute_script("window.stop();")
    #     return elm


class SearchResults:
    def __init__(self, driver: WebDriver):
        self.driver = driver

    def number_of_articles_and_pages(self) -> Tuple[
        int,  # articles
        int,  # pages
        int,  # page size
    ]:
        articles_elem = self.driver.find_element_by_css_selector('td.TitleLeftCell td')
        n_articles = int(re.search(r"\d+", articles_elem.text)[0])

        page_elem = self.driver.find_element_by_css_selector('font.numNow')
        per_page = int(page_elem.text)

        n_pages = ceil(n_articles / per_page)

        return n_articles, n_pages

    def get_structured_elements(self) -> Iterable[Result]:
        "Get elements from html table, row by row."
        rows = self.driver.find_elements_by_xpath(
            '//table[@class="GridTableContent"]//tr[position() > 1]'
        )

        for row in rows:
            yield Result.from_row(row)

    def get_element_and_stop_page(self, *locator) -> WebElement:
        ignored_exceptions = (NoSuchElementException, StaleElementReferenceException)
        wait = WebDriverWait(self.driver, 30, ignored_exceptions=ignored_exceptions)
        elm = wait.until(EC.presence_of_element_located(locator))
        self.driver.execute_script("window.stop();")
        return elm

    def next_page(self) -> None:
        link = self.get_element_and_stop_page(By.LINK_TEXT, "下頁")

        try:
            link.click()
            print("Navigating to Next Page")
        except (TimeoutException, WebDriverException):
            print("Last page reached")


def loop_through_results(driver) -> Iterable[SearchResults]:
    "Iterate through each page of the search result."
    result_page = SearchResults(driver)
    n_articles, n_pages = result_page.number_of_articles_and_pages()

    print(f"{n_articles} found. A maximum of 500 will be retrieved.")

    for page in count(1):

        print(f"Scraping page {page}/{n_pages}")
        print()

        result = result_page.get_structured_elements()
        yield from result

        if page >= n_pages or page >= 10:
            break

        result_page.next_page()
        result_page = SearchResults(driver)


def save_articles(articles: Iterable[SearchResults], file_prefix: str) -> None:
    file_path = Path(file_prefix).with_suffix('.json')

    with file_path.open('w') as file:
        file.write('[\n')
        first = True

        for article in articles:
            if first:
                first = False
            else:
                file.write(',\n')
            json.dump(article.as_dict(), file, ensure_ascii=False, indent=4)

        file.write('\n]\n')


def query(keyword, driver) -> None:
    "Submit query to database."
    page = MainPage(driver)
    page.submit_search(keyword)
    page.switch_to_frame()
    page.max_content()


def search(keyword):
    with Firefox() as driver:
        driver.get('http://cnki.sris.com.tw/kns55')
        query(keyword, driver)

        print("正在搜尋中國期刊網……")
        print(f"關鍵字：「{keyword}」")

        result = loop_through_results(driver)
        # save_articles(result, 'cnki_search_result.json')

        yield from result


if __name__ == '__main__':
    result = search('尹至')
    save_articles(result, 'cnki_search_result.json')
