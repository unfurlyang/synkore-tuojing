from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.providers.base import AudioData, ProviderError
from app.schemas import Preference


def _error_message(action: str, exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        body = exc.response.text[:300].replace("\n", " ")
        return f"{action}服务返回 HTTP {exc.response.status_code}: {body}"
    return f"{action}服务调用失败: {type(exc).__name__}: {exc}"


class OpenAICompatibleASR:
    name = "openai"

    def __init__(self, base_url: str, api_key: str, model: str, timeout: int = 60):
        if not api_key:
            raise ProviderError("ASR_PROVIDER=openai 但未配置 ASR_API_KEY")
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    async def transcribe(self, content: bytes, filename: str, content_type: str) -> str:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        files = {"file": (filename, content, content_type or "application/octet-stream")}
        data = {"model": self.model, "response_format": "json"}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(f"{self.base_url}/audio/transcriptions", headers=headers, data=data, files=files)
                response.raise_for_status()
            text = response.json().get("text", "").strip()
            if not text:
                raise ProviderError("识别服务返回了空文本")
            return text
        except ProviderError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError(_error_message("识别", exc)) from exc


class OpenAICompatibleRewriter:
    name = "openai"

    def __init__(self, base_url: str, api_key: str, model: str, timeout: int, transport: httpx.AsyncBaseTransport | None = None):
        if not api_key:
            raise ProviderError("REWRITE_PROVIDER=openai 但未配置 LLM_API_KEY")
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.transport = transport

    def _request_extras(self) -> dict[str, Any]:
        return {}

    def _messages(self, text: str, preference: Preference, context: str = "", streaming: bool = False) -> list[dict[str, str]]:
        levels = {
            "conservative": "只删除口头填充词、结巴和完全重复，保留其他内容。",
            "standard": "删除口头填充词、重复、寒暄、课堂管理和纯氛围描述，保留全部知识与有信息量的表达。",
            "strong": "执行知识-only 强过滤：只保留学科知识、推理和解题内容，删除所有不含知识的话语。",
        }
        course_rules = (
            "知识内容包括定义、概念、公式、原理、因果、条件、推导、比较、关键例子、解题步骤和结论。"
            "废话包括学习热情、课堂氛围、情绪评价、鼓励寒暄、纪律管理、设备调试、翻页、作业和课程安排、无知识的过渡及重复。"
            "例如‘大家学习热情高涨’必须整句删除，不得保留或改写。"
            "一句话同时包含废话和知识时，只删除废话部分，必须保留知识部分。"
            "关键例子若用于解释知识则保留；不得把知识讲解压缩成课堂纪要或标题。"
        )
        if preference.mode == "style":
            task = (
                "你必须在一次生成中依次完成两个内部步骤，但不要输出步骤或分析："
                f"第一步，{levels[preference.filter_strength]}；"
                "第二步，只把第一步提炼出的知识内容迁移到以下目标教师讲课画像。"
                "风格迁移只能改变语言组织、解释顺序和推理呈现，不能改变知识本身。"
                "教师画像不是内容素材：绝不能为了回顾、举例、类比或解释而补入原文没有的信息，也不能重新加入口头禅和确认语。\n"
                + preference.style_prompt
            )
        else:
            task = levels[preference.filter_strength]
        system = (
            "你是中文课程音频的知识内容编辑器，不是摘要器。"
            + task
            + course_rules
            + "先核对语音识别文本：结合课程上下文修正明确的同音错别字、术语误识别、错误断句和标点，使句子通顺易懂；不确定时保留原样。"
            + "校对只能修正文字形式，不能借纠错改动数字、公式、否定、条件、观点归属或补充知识。"
            + "必须保留知识相关的人名、术语、数字、金额、百分比、单位、时间、地点、否定关系、不确定性和观点归属。"
            + "公式、变量关系和成立条件本身就是知识，即使句子很短也绝不能删除。"
            + "只能压缩和重组原文已经明确说出的知识；不得补充背景、定义、例子、公式、原因或结论。"
            + "原文是疑问句时只清理并保留疑问，不得回答；缺少上下文时不得猜测。"
            + "不得新增原文没有的公式符号或变量名，不得解释处理过程。"
            + "最终文本通常应为原文知识部分长度的30%–80%，除去除废话外不得比原文更长。"
            + (
                "强过滤时若原文完全没有知识内容则只返回空响应。只输出最终播报正文，不要JSON、Markdown、引号、标题或分析。"
                if streaming
                else "强过滤时若原文完全没有知识内容，rewritten_text 返回空字符串。只返回一个 JSON 对象，格式为 {\"rewritten_text\":\"改写后的文本\"}。"
            )
        )
        user_content = text
        if context and context.strip() != text.strip():
            user_content = (
                "以下课程上下文只用于理解指代和消歧，不得把上下文中的其他内容并入结果。\n"
                f"<课程上下文>{context}</课程上下文>\n"
                f"<唯一待处理短段>{text}</唯一待处理短段>"
            )
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ]

    @staticmethod
    def _parse_content(payload: dict[str, Any]) -> str:
        content = payload["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            content = content.strip("`").removeprefix("json").strip()
        try:
            return json.loads(content)["rewritten_text"].strip()
        except (json.JSONDecodeError, KeyError, TypeError):
            start, end = content.find("{"), content.rfind("}")
            if start >= 0 and end > start:
                return json.loads(content[start : end + 1])["rewritten_text"].strip()
            raise

    async def rewrite(self, text: str, preference: Preference, context: str = "") -> str:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {
            "model": self.model,
            "messages": self._messages(text, preference, context),
            "temperature": 0.1,
            "max_tokens": 320,
            "response_format": {"type": "json_object"},
            **self._request_extras(),
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
                response = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
                response.raise_for_status()
            rewritten = self._parse_content(response.json())
            if not rewritten and preference.filter_strength != "strong":
                raise ProviderError("改写服务返回了空文本")
            return rewritten
        except ProviderError:
            raise
        except (httpx.HTTPError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ProviderError(_error_message("改写", exc)) from exc

    async def rewrite_stream(self, text: str, preference: Preference, context: str = "") -> AsyncIterator[str]:
        """Stream final plain text so the first sentence can be synthesized immediately."""
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {
            "model": self.model,
            "messages": self._messages(text, preference, context, streaming=True),
            "temperature": 0.1,
            "max_tokens": 320,
            "stream": True,
            **self._request_extras(),
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
                async with client.stream(
                    "POST", f"{self.base_url}/chat/completions", headers=headers, json=payload
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if not data or data == "[DONE]":
                            continue
                        chunk = json.loads(data)
                        choices = chunk.get("choices") or []
                        if not choices:
                            continue
                        content = (choices[0].get("delta") or {}).get("content")
                        if isinstance(content, str) and content:
                            yield content
        except ProviderError:
            raise
        except (httpx.HTTPError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ProviderError(_error_message("流式改写", exc)) from exc

    async def proofread(self, text: str, context: str = "") -> str:
        """Conservative transcript proofreading for offline teacher-profile ingestion."""
        headers = {"Authorization": f"Bearer {self.api_key}"}
        system = (
            "你是中文课程语音识别校对器。结合上下文只修正明确的同音错别字、术语误识别、断句和标点，"
            "让文本通顺易懂；不确定处原样保留。不得过滤、总结、改写风格、补充知识或回答问题。"
            "数字、公式、变量、单位、否定、条件和观点归属必须原样保留。"
            "只返回JSON：{\"corrected_text\":\"校对后的完整原文\"}。"
        )
        user = f"<课程上下文>{context}</课程上下文>\n<待校对转写>{text}</待校对转写>" if context else text
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0,
            "max_tokens": 8000,
            "response_format": {"type": "json_object"},
            **self._request_extras(),
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
                response = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
                response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"].strip()
            corrected = json.loads(content)["corrected_text"].strip()
            if not corrected:
                raise ProviderError("校对服务返回了空文本")
            return corrected
        except ProviderError:
            raise
        except (httpx.HTTPError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ProviderError(_error_message("转写校对", exc)) from exc

    async def rewrite_post_course(self, text: str, preference: Preference, context: str = "") -> str:
        """Full-course style transfer: preserve the complete lesson, not real-time compression."""
        headers = {"Authorization": f"Bearer {self.api_key}"}
        system = (
            "你是完整课程的课后风格转化编辑器。把已经校对的课程原文迁移到目标教师的表达和思维方式。"
            "这不是实时提炼：必须完整保留原文的知识、公式、条件、疑问、例子、推导和解题步骤，不做知识点摘要。"
            "重点迁移措辞句式、逻辑连接、讲解顺序和推理呈现；不得搬运画像中的知识，不得补充原文没有的背景、答案或结论。"
            "原文疑问可以重述为引导性问题，但不得擅自回答。数字、单位、否定和观点归属必须保持不变。"
            + preference.style_prompt
            + "只返回JSON：{\"rewritten_text\":\"风格转化后的完整课程文本\"}。"
        )
        user = f"<课程上下文>{context}</课程上下文>\n<待转化原文>{text}</待转化原文>" if context else text
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0.2,
            "max_tokens": 6000,
            "response_format": {"type": "json_object"},
            **self._request_extras(),
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
                response = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
                response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"].strip()
            rewritten = json.loads(content)["rewritten_text"].strip()
            if not rewritten:
                raise ProviderError("课后风格转化返回了空文本")
            return rewritten
        except ProviderError:
            raise
        except (httpx.HTTPError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ProviderError(_error_message("课后风格转化", exc)) from exc


class OpenAICompatibleTeacherProfiler:
    """Build an evidence-based lecture style profile; never clones a voice."""

    name = "openai"

    def __init__(self, base_url: str, api_key: str, model: str, timeout: int, transport: httpx.AsyncBaseTransport | None = None):
        if not api_key:
            raise ProviderError("教师画像需要配置语言模型 API Key")
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.transport = transport

    def _request_extras(self) -> dict[str, Any]:
        return {}

    @staticmethod
    def _representative_transcript(transcript: str, limit: int = 24000) -> str:
        if len(transcript) <= limit:
            return transcript
        part = limit // 3
        return (
            transcript[:part]
            + "\n……[中间仅因上下文长度省略，不代表课程中断]……\n"
            + transcript[len(transcript) // 2 - part // 2 : len(transcript) // 2 + part // 2]
            + "\n……[后文采样]……\n"
            + transcript[-part:]
        )

    async def distill(self, transcript: str, teacher_name: str) -> dict[str, list[str]]:
        system = (
            "你是教师表达与思维风格分析器。只能依据给定转写提炼可观察、可复用的表达和推理特征，不能推测人格、情绪、身份或教学水平。"
            "核心任务不是总结教师讲了哪些知识点，而是分析教师怎么表达、怎么组织逻辑、怎么推进推理。"
            "重点观察常用句式与措辞、句子长短、衔接词、设问、类比、强调与重复方式，以及问题提出、条件检查、因果解释、演绎归纳、举例和总结的路径。"
            "不得输出课程知识点清单，不要搬运学科事实，不要把只出现一次的措辞当成稳定风格。"
            "language_features、teaching_structure、thinking_patterns 和 rewrite_rules 只写值得迁移的正向特征；口头禅、填充词、频繁确认语、氛围描述和课堂管理只能放入 avoid_features，不能在正向特征与避免规则中互相矛盾。"
            "rewrite_rules 不得要求补充原文没有的回顾、例子、背景或解释，只能指导如何组织已有知识。"
            "输出应覆盖语言特点、讲课结构、思维方式，以及能直接指导实时改写的规则。"
            "不得模仿口头禅、结巴、无知识寒暄、课堂管理、错误知识或冒犯性表达，也不进行声音克隆。"
            "只返回 JSON：{"
            '"language_features":["3-6条语言特点"],'
            '"teaching_structure":["2-5条讲课结构"],'
            '"thinking_patterns":["2-5条推理与思维路径"],'
            '"rewrite_rules":["4-8条第二人称可执行改写规则"],'
            '"avoid_features":["2-6条不应迁移的表达"],'
            '"evidence":["3-8条来自转写的简短证据"]}'
        )
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": f"教师标记：{teacher_name}\n课程转写：\n{self._representative_transcript(transcript)}"},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            **self._request_extras(),
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
                response = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
                response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"].strip()
            if content.startswith("```"):
                content = content.strip("`").removeprefix("json").strip()
            result = json.loads(content)
            required = ("language_features", "teaching_structure", "thinking_patterns", "rewrite_rules", "avoid_features", "evidence")
            for key in required:
                if not isinstance(result.get(key), list) or not result[key]:
                    raise ProviderError(f"教师画像结果缺少有效字段: {key}")
                result[key] = [str(item).strip() for item in result[key] if str(item).strip()][:10]
            return result
        except ProviderError:
            raise
        except (httpx.HTTPError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ProviderError(_error_message("教师画像蒸馏", exc)) from exc


class OpenAICompatibleTTS:
    name = "openai"

    def __init__(self, base_url: str, api_key: str, model: str, voice: str, timeout: int = 60):
        if not api_key:
            raise ProviderError("TTS_PROVIDER=openai 但未配置 TTS_API_KEY")
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.voice = "alloy" if voice == "default" else voice
        self.timeout = timeout

    async def synthesize(self, text: str) -> AudioData:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {"model": self.model, "voice": self.voice, "input": text, "response_format": "wav"}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(f"{self.base_url}/audio/speech", headers=headers, json=payload)
                response.raise_for_status()
            if not response.content:
                raise ProviderError("合成服务返回了空音频")
            content_type = response.headers.get("content-type", "audio/wav").split(";")[0]
            return AudioData(content=response.content, content_type=content_type, extension=".wav")
        except ProviderError:
            raise
        except httpx.HTTPError as exc:
            raise ProviderError(_error_message("合成", exc)) from exc
