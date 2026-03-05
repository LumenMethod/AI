"""Загрузчик контента из Notion в базу знаний."""
import logging
import httpx
from typing import List, Dict

logger = logging.getLogger(__name__)

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


class NotionLoader:
    def __init__(self, token: str):
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        }

    async def get_all_pages(self) -> List[Dict]:
        """Получить все страницы доступные интеграции."""
        pages = []
        async with httpx.AsyncClient(timeout=30) as client:
            # Ищем все страницы через search
            body = {"filter": {"value": "page", "property": "object"}, "page_size": 100}
            resp = await client.post(f"{NOTION_API}/search", headers=self.headers, json=body)
            resp.raise_for_status()
            data = resp.json()
            pages.extend(data.get("results", []))

            # Пагинация
            while data.get("has_more"):
                body["start_cursor"] = data["next_cursor"]
                resp = await client.post(f"{NOTION_API}/search", headers=self.headers, json=body)
                resp.raise_for_status()
                data = resp.json()
                pages.extend(data.get("results", []))

        logger.info(f"Found {len(pages)} pages in Notion")
        return pages

    async def get_page_content(self, page_id: str) -> str:
        """Извлечь текстовый контент блоков страницы."""
        texts = []
        async with httpx.AsyncClient(timeout=30) as client:
            url = f"{NOTION_API}/blocks/{page_id}/children"
            params = {"page_size": 100}

            while url:
                resp = await client.get(url, headers=self.headers, params=params)
                resp.raise_for_status()
                data = resp.json()

                for block in data.get("results", []):
                    text = self._extract_text(block)
                    if text:
                        texts.append(text)

                if data.get("has_more"):
                    params["start_cursor"] = data["next_cursor"]
                else:
                    break

        return "\n".join(texts)

    def _extract_text(self, block: dict) -> str:
        """Извлечь текст из блока Notion."""
        btype = block.get("type", "")
        block_data = block.get(btype, {})

        # Большинство блоков имеют rich_text
        rich_text = block_data.get("rich_text", [])
        if rich_text:
            return "".join(t.get("plain_text", "") for t in rich_text)

        # Заголовки
        for heading in ("heading_1", "heading_2", "heading_3"):
            if btype == heading:
                texts = block_data.get("rich_text", [])
                return "## " + "".join(t.get("plain_text", "") for t in texts)

        return ""

    def get_page_title(self, page: dict) -> str:
        """Получить заголовок страницы."""
        props = page.get("properties", {})
        for prop in props.values():
            if prop.get("type") == "title":
                titles = prop.get("title", [])
                if titles:
                    return titles[0].get("plain_text", "Без названия")
        return "Без названия"

    async def load_all_documents(self) -> List[Dict]:
        """Загрузить все документы с контентом."""
        pages = await self.get_all_pages()
        documents = []

        for page in pages:
            page_id = page["id"].replace("-", "")
            title = self.get_page_title(page)
            url = page.get("url", "")

            try:
                content = await self.get_page_content(page_id)
                if content.strip():
                    documents.append({
                        "id": page_id,
                        "title": title,
                        "content": f"# {title}\n\n{content}",
                        "url": url,
                        "last_edited": page.get("last_edited_time", ""),
                    })
                    logger.info(f"Loaded: {title} ({len(content)} chars)")
            except Exception as e:
                logger.warning(f"Failed to load page {title}: {e}")

        return documents
