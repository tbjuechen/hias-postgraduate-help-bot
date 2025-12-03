from typing import List, Dict, Optional, Any
import os
import hashlib
import sqlite3
import time
import json
from ..memory.embedding import get_text_embedder, get_dimension
from ..memory.storage.qdrant_store import QdrantVectorStore

from loguru import logger


class DocumentLoader:
    def __init__(self):
        self.markitdown = self._get_markitdown_instance()
    
    @staticmethod
    def _get_markitdown_instance():
        """获取 MarkItDown 实例"""
        try:
            from markitdown import MarkItDown
            return MarkItDown()
        except ImportError:
            raise ImportError("[RAG] 请安装 markitdown 库: pip install markitdown")
    

    def _is_markitdown_support_format(self, path: str) -> bool:
        """
        检查文件格式是否被markitdown支持
        支持: PDF, Office docs, images
        audio, HTML, test formats, zip files, etc.
        """
        ext = (os.path.splitext(path)[1] or "").lower()
        supported_formats = {
            # Documents
            '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
            # Text formats
            '.txt', '.md', '.csv', '.json', '.xml', '.html', '.htm',
            # Images (OCR + metadata)
            '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.webp',
            # Audio (transcription + metadata) 
            '.mp3', '.wav', '.m4a', '.aac', '.flac', '.ogg',
            # Archives
            '.zip', '.tar', '.gz', '.rar',
            # Code files
            '.py', '.js', '.ts', '.java', '.cpp', '.c', '.h', '.css', '.scss',
            # Other text
            '.log', '.conf', '.ini', '.cfg', '.yaml', '.yml', '.toml'
        }
        return ext in supported_formats

    def load(self, path: str) -> str:
        """
        使用 markitdown 将文件转换为 markdown 格式的文本
        """
        if not os.path.exists(path):
            return ""
        
        # 对PDF文件只用增强处理
        ext = (os.path.splitext(path)[1] or "").lower()
        if ext == '.pdf':
            return self._enhanced_pdf_processing(path)
        
        # 对其他格式使用 markitdown 转换
        if self.markitdown is None:
            return self._fallback_text_reader(path)
        
        try:
            result = self.markitdown.convert(path)
            text = getattr(result, 'text_content', None)
            if isinstance(text, str) and text.strip():
                return text
            return ""
        except Exception as e:
            logger.warning(f"[RAG] MarkItDown 转换失败: {e}")
            return self._fallback_text_reader(path)
        
    def _enhanced_pdf_processing(self, path: str) -> str:
        """
        对 PDF 文件进行增强处理，结合 OCR 和文本提取
        """
        logger.info(f"[RAG] 对 PDF 文件进行增强处理: {path}")

        # 使用 markitdown 提取文本
        if self.markitdown is not None:
            return self._fallback_text_reader(path)
        
        try:
            result = self.markitdown.convert(path)
            raw_text = getattr(result, 'text_content', None)
            if not raw_text or not raw_text.strip():
                return ""
        
            # 后处理
            cleaned_text = self._post_process_pdf_text(raw_text)
            logger.debug(f"[RAG] PDF 后处理完成：{len(raw_text)} -> {len(cleaned_text)} 字符")
            return cleaned_text
        
        except Exception as e:
            logger.warning(f"[RAG] PDF 增强处理失败: {e}")
            return self._fallback_text_reader(path)
        
    def _post_process_pdf_text(self, text: str) -> str:
        """
        对提取的 PDF 文本进行后处理，去除多余的空白和格式问题
        """
        import re

        # 1. 按行分割并清理
        lines = text.splitlines()
        cleaned_lines = []

        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # 移除单个字符的行
            if len(line) <= 2 and not line.isdigit():
                continue

            # 移除页码行
            if re.match(r'^\d+$', line):  # 纯数字行（页码）
                continue
            if line.lower() in ['github', 'project', 'forks', 'stars', 'language']:
                continue

            cleaned_lines.append(line)
        
        # 2. 合并行，处理断行问题
        merged_lines = []
        i = 0
        
        while i < len(cleaned_lines):
            current_line = cleaned_lines[i]
            
            # 如果当前行很短，尝试与下一行合并
            if len(current_line) < 60 and i + 1 < len(cleaned_lines):
                next_line = cleaned_lines[i + 1]
                
                # 合并条件：都是内容，不是标题
                if (not current_line.endswith('：') and 
                    not current_line.endswith(':') and
                    not current_line.startswith('#') and
                    not next_line.startswith('#') and
                    len(next_line) < 120):
                    
                    merged_line = current_line + " " + next_line
                    merged_lines.append(merged_line)
                    i += 2  # 跳过下一行
                    continue
            
            merged_lines.append(current_line)
            i += 1
        
        # 3. 重新组织段落
        paragraphs = []
        current_paragraph = []
        
        for line in merged_lines:
            # 检查是否是新段落的开始
            if (line.startswith('#') or  # 标题
                line.endswith('：') or   # 中文冒号结尾
                line.endswith(':') or    # 英文冒号结尾
                len(line) > 150 or       # 长句通常是段落开始
                not current_paragraph):  # 第一行
                
                # 保存当前段落
                if current_paragraph:
                    paragraphs.append(' '.join(current_paragraph))
                    current_paragraph = []
                
                paragraphs.append(line)
            else:
                current_paragraph.append(line)
        
        # 添加最后一个段落
        if current_paragraph:
            paragraphs.append(' '.join(current_paragraph))

        
        return '\n\n'.join(paragraphs)
    
    def _fallback_text_reader(self, path: str) -> str:
        """
        备用的文本读取方法，适用于简单的文本文件
        """
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        except Exception as e:
            try:
                with open(path, 'r', encoding='latin-1', errors='ignore') as f:
                    return f.read()
            except Exception as e:
                return ""
            

class TextSplitter:
    def __init__(self, chunk_size: int = 800, overlap: int = 100):
        self.chunk_size = chunk_size
        self.overlap = overlap
    
    @staticmethod
    def _dectect_lang(sample: str) -> str:
        try:
            from langdetect import detect
            return detect(sample[:1000]) if sample else 'unknown'
        except Exception:
            return 'unknown'
        
    @staticmethod
    def _is_cjk(ch: str) -> bool:
        """检查字符是否为中日韩字符"""
        code = ord(ch)
        return (
            0x4E00 <= code <= 0x9FFF or
            0x3400 <= code <= 0x4DBF or
            0x20000 <= code <= 0x2A6DF or
            0x2A700 <= code <= 0x2B73F or
            0x2B740 <= code <= 0x2B81F or
            0x2B820 <= code <= 0x2CEAF or
            0xF900 <= code <= 0xFAFF
        )
    
    @staticmethod
    def _approx_token_len(text: str) -> int:
        # 近似估计：CJK字符按1 token，其他按空白分词
        cjk = sum(1 for ch in text if TextSplitter._is_cjk(ch))
        non_cjk_tokens = len([t for t in text.split() if t])
        return cjk + non_cjk_tokens
    
    @staticmethod
    def _split_paragraphs_with_headings(text: str) -> List[Dict]:
        lines = text.splitlines()
        heading_stack: List[str] = []
        paragraphs: List[Dict] = []
        buf: List[str] = []
        char_pos = 0
        def flush_buf(end_pos: int):
            if not buf:
                return
            content = "\n".join(buf).strip()
            if not content:
                return
            paragraphs.append({
                "content": content,
                "heading_path": " > ".join(heading_stack) if heading_stack else None,
                "start": max(0, end_pos - len(content)),
                "end": end_pos,
            })
        for ln in lines:
            raw = ln
            if raw.strip().startswith("#"):
                # heading line
                flush_buf(char_pos)
                level = len(raw) - len(raw.lstrip('#'))
                title = raw.lstrip('#').strip()
                if level <= 0:
                    level = 1
                if level <= len(heading_stack):
                    heading_stack = heading_stack[:level-1]
                heading_stack.append(title)
                char_pos += len(raw) + 1
                continue
            # paragraph accumulation
            if raw.strip() == "":
                flush_buf(char_pos)
                buf = []
            else:
                buf.append(raw)
            char_pos += len(raw) + 1
        flush_buf(char_pos)
        if not paragraphs:
            paragraphs = [{"content": text, "heading_path": None, "start": 0, "end": len(text)}]
        return paragraphs
    
    def _chunk_paragraphs(self, paragraphs: List[Dict]) -> List[Dict]:
        chunks: List[Dict] = []
        cur: List[Dict] = []
        cur_tokens = 0
        i = 0
        while i < len(paragraphs):
            p = paragraphs[i]
            p_tokens = self._approx_token_len(p["content"]) or 1
            if cur_tokens + p_tokens <= self.chunk_size or not cur:
                cur.append(p)
                cur_tokens += p_tokens
                i += 1
            else:
                # emit current chunk
                content = "\n\n".join(x["content"] for x in cur)
                start = cur[0]["start"]
                end = cur[-1]["end"]
                heading_path = next((x["heading_path"] for x in reversed(cur) if x.get("heading_path")), None)
                chunks.append({
                    "content": content,
                    "start": start,
                    "end": end,
                    "heading_path": heading_path,
                })
                # build overlap by keeping tail tokens
                if self.overlap > 0 and cur:
                    kept: List[Dict] = []
                    kept_tokens = 0
                    for x in reversed(cur):
                        t = self._approx_token_len(x["content"]) or 1
                        if kept_tokens + t > self.overlap:
                            break
                        kept.append(x)
                        kept_tokens += t
                    cur = list(reversed(kept))
                    cur_tokens = kept_tokens
                else:
                    cur = []
                    cur_tokens = 0
        if cur:
            content = "\n\n".join(x["content"] for x in cur)
            start = cur[0]["start"]
            end = cur[-1]["end"]
            heading_path = next((x["heading_path"] for x in reversed(cur) if x.get("heading_path")), None)
            chunks.append({
                "content": content,
                "start": start,
                "end": end,
                "heading_path": heading_path,
            })
        return chunks

    def split(self, text: str, namespace: Optional[str] = None, source_label: str = "rag", **kwargs)-> List[Dict]:
        """
        将文本拆分为多个块
        """
        chunks: List[Dict] = []
        seen_hashes = set()

        lang = self._dectect_lang(text)
        doc_id = hashlib.md5(text[:1000].encode('utf-8')).hexdigest()

        para = self._split_paragraphs_with_headings(text)
        token_chunks = self._chunk_paragraphs(para)

        for ch in token_chunks:
            content = ch["content"]
            start = ch.get("start", 0)
            end = ch.get("end", start + len(content))
            norm = content.strip()
            if not norm:
                continue
                
            content_hash = hashlib.md5(norm.encode('utf-8')).hexdigest()
            if content_hash in seen_hashes:
                continue
            seen_hashes.add(content_hash)
            
            chunk_id = hashlib.md5(f"{doc_id}|{start}|{end}|{content_hash}".encode('utf-8')).hexdigest()
            chunks.append({
                "id": chunk_id,
                "content": content,
                "metadata": {
                    "source_path": kwargs.get("source_path", ""),
                    "file_ext": kwargs.get("file_ext", ""),
                    "doc_id": doc_id,
                    "lang": lang,
                    "start": start,
                    "end": end,
                    "content_hash": content_hash,
                    "namespace": namespace or "default",
                    "source": source_label,
                    "external": True,
                    "heading_path": ch.get("heading_path"),
                    "format": "markdown",  # Mark all content as markdown-processed
                },
            })

        logger.info(f"[RAG] 文本拆分为 {len(chunks)} 个块 (语言: {lang})")
        return chunks

class StorageManager:
    def __init__(self):
        self.vector_store: Optional[QdrantVectorStore] = self._create_default_vector_store()
        self.embedder = get_text_embedder()
        self.dimension = get_dimension(384)

    @staticmethod
    def _preprocess_markdown_metadata(text: str) -> str:
        """
        预处理 markdown 文本来获得更好的嵌入质量
        移除多余的标记，保留语义内容
        """
        import re

        # Remove markdown headers symbols but keep the text
        text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
        
        # Remove markdown links but keep the text
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
        
        # Remove markdown emphasis markers
        text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)  # bold
        text = re.sub(r'\*([^*]+)\*', r'\1', text)      # italic
        text = re.sub(r'`([^`]+)`', r'\1', text)        # inline code
        
        # Remove markdown code blocks but keep content
        text = re.sub(r'```[^\n]*\n([\s\S]*?)```', r'\1', text)
        
        # Remove excessive whitespace
        text = re.sub(r'\n\s*\n', '\n\n', text)
        text = re.sub(r'[ \t]+', ' ', text)
        
        return text.strip()

    def _create_default_vector_store(self, dimension: int = None) -> QdrantVectorStore:
        """
        创建默认的向量存储
        """
        if dimension is None:
            dimension = get_dimension(384)
    
        # Check for Qdrant configuration
        qdrant_url = os.getenv("QDRANT_URL", None)
        qdrant_api_key = os.getenv("QDRANT_API_KEY", None)
        
        # 使用连接管理器
        from ..memory.storage.qdrant_store import QdrantConnectionManager
        return QdrantConnectionManager.get_instance(
            url=qdrant_url,
            api_key=qdrant_api_key,
            collection_name="rag_vectors",
            vector_size=dimension,
            distance="cosine"
        )
    
    def index_chunks(
        self,
        chunks: List[Dict],
        cache_db: Optional[str] = None,
        batch_size: int = 64,
        rag_namespace: str = "default",
    ):
        """
        使用统一嵌入和Qdrant存储对文本块进行索引
        """
        if not chunks:
            logger.warning("[RAG] 没有提供任何文本块进行索引")
            return
        
        processed_texts = []
        for c in chunks:
            raw_content = c["content"]
            processed_content = self._preprocess_markdown_metadata(raw_content)
            processed_texts.append(processed_content)

        logger.info(f"[RAG] 嵌入开始: 总共 {len(chunks)} 个文本块，分批大小 {batch_size}")

        vecs: List[List[float]] = []
        for i in range(0, len(processed_texts), batch_size):
            part = processed_texts[i:i+batch_size]
            try:
                part_vecs = self.embedder.encode(part)

                if not isinstance(part_vecs, list):
                    if hasattr(part_vecs, "tolist"):
                        part_vecs = [part_vecs.tolist()]
                    else:
                        part_vecs = [list(part_vecs)]
                else:
                    # 检查是否为嵌套列表
                    if part_vecs and not isinstance(part_vecs[0], (list, tuple)) and hasattr(part_vecs[0], "__len__"):
                        # numpy数组列表 -> 转换每个数组
                        normalized_vecs = []
                        for v in part_vecs:
                            if hasattr(v, "tolist"):
                                normalized_vecs.append(v.tolist())
                            else:
                                normalized_vecs.append(list(v))
                        part_vecs = normalized_vecs
                    elif part_vecs and not isinstance(part_vecs[0], (list, tuple)):
                        # 单个向量被误判为列表，实际应该包装成[[...]]
                        if hasattr(part_vecs, "tolist"):
                            part_vecs = [part_vecs.tolist()]
                        else:
                            part_vecs = [list(part_vecs)]
                
                for v in part_vecs:
                    try:
                        # 确保向量是float列表
                        if hasattr(v, "tolist"):
                            v = v.tolist()
                        v_norm = [float(x) for x in v]
                        if len(v_norm) != self.dimension:
                            logger.warning(f"[RAG] 向量维度异常: 期望{self.dimension}, 实际{len(v_norm)}")
                            # 用零向量填充或截断
                            if len(v_norm) < self.dimension:
                                v_norm.extend([0.0] * (self.dimension - len(v_norm)))
                            else:
                                v_norm = v_norm[:self.dimension]
                        vecs.append(v_norm)
                    except Exception as e:
                        logger.warning(f"[RAG] 向量转换失败: {e}, 使用零向量")
                        vecs.append([0.0] * self.dimension)
            
            except Exception as e:
                logger.warning(f"[RAG] Batch {i} encoding failed: {e}")
                logger.info(f"[RAG] Retrying batch {i} with smaller chunks...")
                
                # 尝试重试：将批次分解为更小的块
                success = False
                for j in range(0, len(part), 8):  # 更小的批次
                    small_part = part[j:j+8]
                    try:
                        import time
                        time.sleep(2)  # 等待2秒避免频率限制
                        
                        small_vecs = self.embedder.encode(small_part)
                        # Normalize to List[List[float]]
                        if isinstance(small_vecs, list) and small_vecs and not isinstance(small_vecs[0], list):
                            small_vecs = [small_vecs]
                        
                        for v in small_vecs:
                            if hasattr(v, "tolist"):
                                v = v.tolist()
                            try:
                                v_norm = [float(x) for x in v]
                                if len(v_norm) != self.dimension:
                                    logger.warning(f"[RAG] 向量维度异常: 期望{self.dimension}, 实际{len(v_norm)}")
                                    if len(v_norm) < self.dimension:
                                        v_norm.extend([0.0] * (self.dimension - len(v_norm)))
                                    else:
                                        v_norm = v_norm[:self.dimension]
                                vecs.append(v_norm)
                                success = True
                            except Exception as e2:
                                logger.warning(f"[RAG] 小批次向量转换失败: {e2}")
                                vecs.append([0.0] * self.dimension)
                    except Exception as e2:
                        logger.warning(f"[RAG] 小批次 {j//8} 仍然失败: {e2}")
                        # 为这个小批次创建零向量
                        for _ in range(len(small_part)):
                            vecs.append([0.0] * self.dimension)
                    
                if not success:
                    logger.error(f"[RAG] 批次 {i} 完全失败，使用零向量")

            logger.info(f"[RAG] Embedding progress: {min(i+batch_size, len(processed_texts))}/{len(processed_texts)}")
        
        # 准备元数据
        metas: List[Dict] = []
        ids: List[str] = []
        for ch in chunks:
            meta = {
                "memory_id": ch["id"],
                "user_id": "system",
                "memory_type": "rag_chunk",
                "content": ch["content"],
                "data_sorce": "rag_client",
                "rag_namespace": rag_namespace,
                "is_rag_data": True
            }

            meta.update(ch.get("metadata", {}))
            metas.append(meta)
            ids.append(ch["id"])
        
        logger.debug(f"[RAG] 准备插入 {len(vecs)} 个向量到向量存储")
        success = self.vector_store.add_vector(
            ids=ids,
            vectors=vecs,
            metadatas=metas,
        )
        if success:
            logger.info(f"[RAG] 成功索引 {len(vecs)} 个文本块到向量存储")
        else:
            logger.error(f"[RAG] 文本块插入失败")
            raise RuntimeError("Failed to insert chunks into vector store")
        
    def embed_query(self, query: str) -> List[float]:
        """
        对查询文本进行嵌入
        """
        try:
            vec = self.embedder.encode(query)

            if hasattr(vec, "tolist"):
                vec = vec.tolist()
            
            # 处理嵌套列表情况
            if isinstance(vec, list) and vec and isinstance(vec[0], (list, tuple)):
                vec = vec[0] 

            # 确保是 float 列表
            result = [float(x) for x in vec]

            # 检查维度
            if len(result) != self.dimension:
                logger.warning(f"[RAG] Query向量维度异常: 期望{self.dimension}, 实际{len(result)}")
                # 用零向量填充或截断
                if len(result) < self.dimension:
                    result.extend([0.0] * (self.dimension - len(result)))
                else:
                    result = result[:self.dimension]
            
            return result

        except Exception as e:
            logger.error(f"[RAG] 查询嵌入失败: {e}")
            return [0.0] * self.dimension

    def search_vectors(
        self,
        query: str = "",
        top_k: int = 8,
        rag_namespace: Optional[str] = None,
        only_rag_data: bool = True,
        score_threshold: Optional[float] = None,
    ) -> List[Dict]:
        """
        使用嵌入的查询向量在向量存储中搜索相似文本块

        :param query: 查询文本
        :param top_k: 返回的最相似文本块数量
        :param rag_namespace: 可选的命名空间过滤
        :param only_rag_data: 是否只返回标记为 RAG 数据的块
        :param score_threshold: 可选的相似度分数阈值过滤
        :return: 返回的相似文本块列表
        """
        if not query:
            return []
        
        qv = self.embed_query(query)

        where = {"memory_type": "rag_chunk"}

        if only_rag_data:
            where["is_rag_data"] = True
            where["data_sorce"] = "rag_client"
        if rag_namespace:
            where["rag_namespace"] = rag_namespace

        try:
            return  self.vector_store.search_vectors(
                query_vector=qv,
                top_k=top_k,
                where=where,
                score_threshold=score_threshold,
            )
        except Exception as e:
            logger.error(f"[RAG] 向量搜索失败: {e}")
            return []
    
class Ranker:
    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        # try load cross encoder
        try:
            from sentence_transformers import CrossEncoder
            self.ranker = CrossEncoder(model_name)
        except ImportError:
            self.ranker = None
            logger.warning(f"[RAG] 请安装 sentence-transformers 库以使用 Ranker: pip install sentence-transformers")
    
    def rank_by_cross_encoder(
        self,
        query: str,
        items: List[Dict],
        top_k: int = 10,
    ) -> List[Dict]:
        """
        使用交叉编码器对检索到的文本块进行重新排序

        :param query: 查询文本
        :param items: 检索到的文本块列表
        :param top_k: 返回的最相关文本块数量
        :return: 返回重新排序后的文本块列表
        """
        if not self.ranker or not items:
            return items[:top_k]
        
        pairs = [(query, item.get("content", "")) for item in items]
        try:
            scores = self.ranker.predict(pairs)
            for item, score in zip(items, scores):
                item["rank_score"] = float(score)
            # 按分数降序排序
            items.sort(key=lambda x: x.get("rerank_score", x.get("score", 0.0)), reverse=True)
            return items[:top_k]
        except Exception as e:
            logger.error(f"[RAG] 排序失败: {e}")
            return items[:top_k]

    def compute_graph_signal(
        self,
        vector_hits: List[Dict],
        same_doc_weight: float = 1.0,
        proximity_weight: float = 1.0,
        proximity_window_chars: int = 1600,
    ) -> Dict[str, float]:
        """
        计算图信号分数以重新排序文本块

        :param vector_hits: 检索到的文本块列表
        :param same_doc_weight: 来自同一文档的块的权重
        :param proximity_weight: 基于位置接近性的权重
        :param proximity_window_chars: 位置接近性的字符窗口大小
        :return: 包含图信号分数的文本块字典
        """
        
        # group by doc
        by_doc: Dict[str, List[Dict]] = {}
        for h in vector_hits:
            meta = h.get("metadata", {})
            did = meta.get("doc_id")
            if not did:
                # fall back to memory_id grouping if doc missing
                did = meta.get("memory_id") or h.get("id")
            by_doc.setdefault(did, []).append(h)

        # same-doc density score
        doc_counts = {d: len(arr) for d, arr in by_doc.items()}
        max_count = max(doc_counts.values()) if doc_counts else 1

        graph_signal: Dict[str, float] = {}
        for did, arr in by_doc.items():
            arr.sort(key=lambda x: x.get("metadata", {}).get("start", 0))
            # precompute density
            density = doc_counts.get(did, 1) / max_count
            # proximity accumulation
            for i, h in enumerate(arr):
                mid = h.get("metadata", {}).get("memory_id", h.get("id"))
                pos_i = h.get("metadata", {}).get("start", 0)
                prox_acc = 0.0
                # look around neighbors within window
                # two-pointer expansion
                # left
                j = i - 1
                while j >= 0:
                    pos_j = arr[j].get("metadata", {}).get("start", 0)
                    dist = abs(pos_i - pos_j)
                    if dist > proximity_window_chars:
                        break
                    prox_acc += max(0.0, 1.0 - (dist / max(1.0, float(proximity_window_chars))))
                    j -= 1
                # right
                j = i + 1
                while j < len(arr):
                    pos_j = arr[j].get("metadata", {}).get("start", 0)
                    dist = abs(pos_i - pos_j)
                    if dist > proximity_window_chars:
                        break
                    prox_acc += max(0.0, 1.0 - (dist / max(1.0, float(proximity_window_chars))))
                    j += 1
                # combine
                score = same_doc_weight * density + proximity_weight * prox_acc
                graph_signal[mid] = graph_signal.get(mid, 0.0) + score

        # normalize to [0,1]
        if graph_signal:
            max_v = max(graph_signal.values())
            if max_v > 0:
                for k in list(graph_signal.keys()):
                    graph_signal[k] = graph_signal[k] / max_v
        return graph_signal

    def rank(
        self,
        vector_hits: List[Dict],
        graph_signals: Optional[Dict[str, float]] = None,
        w_vector: float = 0.7,
        w_graph: float = 0.3,
    ) -> List[Dict]:
        """
        综合向量相似度和图信号对文本块进行排序

        :param vector_hits: 检索到的文本块列表
        :param graph_signals: 图信号分数字典
        :param w_vector: 向量相似度权重
        :param w_graph: 图信号权重
        :return: 返回排序后的文本块列表
        """
        items: List[Dict] = []
        graph_signals = graph_signals or {}
        for h in vector_hits:
            mid = h.get("metadata", {}).get("memory_id", h.get("id"))
            g = float(graph_signals.get(mid, 0.0))
            v = float(h.get("score", 0.0))
            score = w_vector * v + w_graph * g
            items.append({
                "memory_id": mid,
                "score": score,
                "vector_score": v,
                "graph_score": g,
                "content": h.get("metadata", {}).get("content", ""),
                "metadata": h.get("metadata", {}),
            })
        
        items.sort(key=lambda x: x['score'], reverse=True)
        
        return items
    
class RAGClient:
    def __init__(self, namespace: str = "default", chunk_size: int = 800, overlap: int = 100):
        """
        初始化 RAG 客户端，硬编码组装所有组件
        """
        self.namespace = namespace
        
        self.loader = DocumentLoader()
        self.splitter = TextSplitter(chunk_size, overlap)
        self.storage = StorageManager()
        self.ranker = Ranker()

    def add_documents(self, file_paths: List[str]):
        """
        添加知识文档
        """
        chunks = []
        for path in file_paths:
            text = self.loader.load(path)
            if not text:
                logger.warning(f"[RAG] 无法加载文件: {path}")
                continue
            file_ext = os.path.splitext(path)[1].lower()
            file_chunks = self.splitter.split(
                text,
                namespace=self.namespace,
                source_path=path,
                file_ext=file_ext,
            )
            chunks.extend(file_chunks)
        
        self.storage.index_chunks(
            chunks,
            rag_namespace=self.namespace,
        )
        return len(chunks)
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取 RAG 存储的统计信息
        """
        return self.storage.vector_store.get_collection_stats()
    
    def merge_snippets(
        self,
        ranked_items: List[Dict],
        max_chars: int = 1200,
    ) -> str:
        """
        合并排名靠前的文本块为单一上下文字符串

        :param ranked_items: 排名靠前的文本块列表
        :param max_chars: 合并后字符串的最大字符数
        :return: 合并后的上下文字符串
        """
        out: List[str] = []
        total = 0
        for it in ranked_items:
            text = it.get("content", "").strip()
            if not text:
                continue
            if total + len(text) > max_chars:
                remain = max_chars - total
                if remain <= 0:
                    break
                out.append(text[:remain])
                total += remain
                break
            out.append(text)
            total += len(text)
        return "\n\n".join(out)
    
    def expand_neighbors_from_pool(
        self,
        selected: List[Dict],
        pool: List[Dict],
        neighbors: int = 1,
        max_additions: int = 5,
    ) -> List[Dict]:
        """
        从候选池中扩展选定的文本块，添加邻近块以丰富上下文
        
        :param selected: 已选定的文本块列表
        :param pool: 候选文本块池
        :param neighbors: 每侧添加的邻近块数量
        :param max_additions: 最大添加的块数量
        :return: 扩展后的文本块列表
        """
        if not selected or not pool or neighbors <= 0:
            return selected
        # index pool by doc_id and sort by start
        by_doc: Dict[str, List[Dict]] = {}
        for it in pool:
            meta = it.get("metadata", {})
            did = meta.get("doc_id")
            if not did:
                continue
            by_doc.setdefault(did, []).append(it)
        for did, arr in by_doc.items():
            arr.sort(key=lambda x: (x.get("metadata", {}).get("start", 0)))
        selected_ids = set(it.get("memory_id") for it in selected)
        additions: List[Dict] = []
        for it in selected:
            meta = it.get("metadata", {})
            did = meta.get("doc_id")
            if not did or did not in by_doc:
                continue
            arr = by_doc[did]
            # find index
            try:
                idx = next(i for i, x in enumerate(arr) if x.get("memory_id") == it.get("memory_id"))
            except StopIteration:
                continue
            for offset in range(1, neighbors + 1):
                for j in (idx - offset, idx + offset):
                    if 0 <= j < len(arr):
                        cand = arr[j]
                        mid = cand.get("memory_id")
                        if mid not in selected_ids:
                            additions.append(cand)
                            selected_ids.add(mid)
                            if len(additions) >= max_additions:
                                break
                if len(additions) >= max_additions:
                    break
            if len(additions) >= max_additions:
                break
        # keep relative order by score
        extended = list(selected) + additions
        extended.sort(key=lambda x: (x.get("rerank_score", x.get("score", 0.0))), reverse=True)
        return extended
    
    def merge_snippets_grouped(
        self,
        ranked_items: List[Dict],
        max_chars: int = 1200,
        include_citations: bool = True,
    ) -> str:
       # Group by doc_id and aggregate doc score
        by_doc: Dict[str, List[Dict]] = {}
        doc_score: Dict[str, float] = {}
        for it in ranked_items:
            meta = it.get("metadata", {})
            did = meta.get("doc_id") or meta.get("source_path") or "unknown"
            by_doc.setdefault(did, []).append(it)
            doc_score[did] = doc_score.get(did, 0.0) + float(it.get("score", 0.0))
        # Sort docs by aggregate score
        ordered_docs = sorted(by_doc.keys(), key=lambda d: doc_score.get(d, 0.0), reverse=True)
        # Within doc, order by start offset to preserve context
        for d in ordered_docs:
            by_doc[d].sort(key=lambda x: (x.get("metadata", {}).get("start", 0)))
        out: List[str] = []
        citations: List[Dict] = []
        total = 0
        cite_index = 1
        for did in ordered_docs:
            parts = by_doc[did]
            for it in parts:
                text = (it.get("content", "") or "").strip()
                if not text:
                    continue
                # add citation marker if enabled
                suffix = ""
                if include_citations:
                    suffix = f" [{cite_index}]"
                need = len(text) + (len(suffix) if suffix else 0)
                if total + need > max_chars:
                    remain = max_chars - total
                    if remain <= 0:
                        break
                    clipped = text[: max(0, remain - len(suffix))]
                    if clipped:
                        out.append(clipped + suffix)
                        total += len(clipped) + len(suffix)
                        if include_citations:
                            m = it.get("metadata", {})
                            citations.append({
                                "index": cite_index,
                                "source_path": m.get("source_path"),
                                "doc_id": m.get("doc_id"),
                                "start": m.get("start"),
                                "end": m.get("end"),
                                "heading_path": m.get("heading_path"),
                            })
                            cite_index += 1
                    break
                out.append(text + suffix)
                total += need
                if include_citations:
                    m = it.get("metadata", {})
                    citations.append({
                        "index": cite_index,
                        "source_path": m.get("source_path"),
                        "doc_id": m.get("doc_id"),
                        "start": m.get("start"),
                        "end": m.get("end"),
                        "heading_path": m.get("heading_path"),
                    })
                    cite_index += 1
            if total >= max_chars:
                break
        merged = "\n\n".join(out)
        if include_citations and citations:
            lines: List[str] = [merged, "", "References:"]
            for c in citations:
                loc = ""
                if c.get("start") is not None and c.get("end") is not None:
                    loc = f" ({c['start']}-{c['end']})"
                hp = f" – {c['heading_path']}" if c.get("heading_path") else ""
                sp = c.get("source_path") or c.get("doc_id") or "source"
                lines.append(f"[{c['index']}] {sp}{loc}{hp}")
            return "\n".join(lines)
        return merged
    
    def compress_ranked_items(
        self,
        ranked_items: List[Dict],
        enable_compression: bool = True,
        max_per_doc: int =2,
        join_gap: int = 200,
    ) -> List[Dict]:
        """
        压缩排名靠前的文本块以减少冗余

        :param ranked_items: 排名靠前的文本块列表
        :param enable_compressionL: 是否启用压缩
        :param max_per_doc: 每个文档保留的最大块数
        :param join_gap: 合并块之间的最大字符间隔
        :return: 压缩后的文本块列表
        """
        if not enable_compression:
            return ranked_items
        by_doc_count: Dict[str, int] = {}
        last_by_doc: Dict[str, Dict] = {}
        new_items: List[Dict] = []
        for it in ranked_items:
            meta = it.get("metadata", {})
            did = meta.get("doc_id") or meta.get("source_path") or "unknown"
            start = int(meta.get("start") or 0)
            end = int(meta.get("end") or (start + len(it.get("content", "") or "")))
            if did not in last_by_doc:
                last_by_doc[did] = it
                by_doc_count[did] = 1
                new_items.append(it)
                continue
            last = last_by_doc[did]
            lmeta = last.get("metadata", {})
            lstart = int(lmeta.get("start") or 0)
            lend = int(lmeta.get("end") or (lstart + len(last.get("content", "") or "")))
            if start - lend <= join_gap and start >= lstart:
                # merge into last
                merged_text = (last.get("content", "") or "").strip()
                add_text = (it.get("content", "") or "").strip()
                if add_text:
                    if merged_text:
                        merged_text = merged_text + "\n\n" + add_text
                    else:
                        merged_text = add_text
                    last["content"] = merged_text
                    lmeta["end"] = max(lend, end)
                    # keep the higher score
                    try:
                        last["score"] = max(float(last.get("score", 0.0)), float(it.get("score", 0.0)))
                    except Exception:
                        pass
                last_by_doc[did] = last
            else:
                cnt = by_doc_count.get(did, 0)
                if cnt >= max_per_doc:
                    continue
                new_items.append(it)
                last_by_doc[did] = it
                by_doc_count[did] = cnt + 1
        return new_items

    def search(
        self,
        query: str,
        top_k: int = 8,
        score_threshold: Optional[float] = None,
    ):
        """
        简单搜索 RAG 知识库

        :param query: 查询文本
        :param top_k: 返回的最相似文本块数量
        :param score_threshold: 可选的相似度分数阈值过滤
        :return: 返回的相似文本块列表
        """
        return self.storage.search_vectors(
            query=query,
            top_k=top_k,
            rag_namespace=self.namespace,
            only_rag_data=True,
            score_threshold=score_threshold,
        )
    
    def search_advanced(
        self,
        query: str,
        top_k: int = 30,  # 增加初始召回数量以支持后续重排序
        rerank_top_k: int = 8,
        score_threshold: Optional[float] = None,
        # Graph Rerank params
        enable_graph_rerank: bool = True,
        same_doc_weight: float = 1.0,
        proximity_weight: float = 1.0,
        proximity_window_chars: int = 1600,
        w_vector: float = 0.7,
        w_graph: float = 0.3,
        # Cross Encoder params
        enable_cross_encoder: bool = True,
        # Context Expansion params
        enable_expansion: bool = False,
        expansion_neighbors: int = 1,
        # Compression params
        enable_compression: bool = True,
    ) -> List[Dict]:
        """
        高级搜索 RAG 知识库，包含图信号重排序、交叉编码器精排、上下文扩展和结果压缩

        :param query: 查询文本
        :param top_k: 初始向量检索的数量
        :param rerank_top_k: 最终返回的文本块数量
        :param score_threshold: 可选的相似度分数阈值过滤
        :param enable_graph_rerank: 是否启用图信号重新排序
        :param same_doc_weight: 图信号中同一文档权重
        :param proximity_weight: 图信号中位置接近性权重
        :param proximity_window_chars: 图信号中位置接近性字符窗口大小
        :param w_vector: 综合排序中向量相似度权重
        :param w_graph: 综合排序中图信号权重
        :param enable_cross_encoder: 是否启用交叉编码器进行精排 (需要安装 sentence-transformers)
        :param enable_expansion: 是否启用上下文扩展 (尝试找回相邻块)
        :param expansion_neighbors: 扩展时每侧添加的邻近块数量
        :param enable_compression: 是否启用结果压缩 (合并相邻块)
        :return: 返回处理后的文本块列表
        """
        # 1. 初始向量检索
        vector_hits = self.storage.search_vectors(
            query=query,
            top_k=top_k,
            rag_namespace=self.namespace,
            only_rag_data=True,
            score_threshold=score_threshold,
        )
        if not vector_hits:
            return []
        
        # 2. 图信号重排序 (Graph Signal Reranking)
        # 利用文档密度和位置信息调整分数
        graph_signals = {}
        if enable_graph_rerank:
            graph_signals = self.ranker.compute_graph_signal(
                vector_hits,
                same_doc_weight=same_doc_weight,
                proximity_weight=proximity_weight,
                proximity_window_chars=proximity_window_chars,
            )
        
        ranked_items = self.ranker.rank(
            vector_hits,
            graph_signals=graph_signals,
            w_vector=w_vector,
            w_graph=w_graph,
        )

        # 3. 交叉编码器精排 (Cross-Encoder Reranking)
        # 使用更精准的模型对结果进行打分
        if enable_cross_encoder:
            ranked_items = self.ranker.rank_by_cross_encoder(
                query, 
                ranked_items, 
                top_k=len(ranked_items)
            )

        # 4. 上下文扩展 (Context Expansion)
        # 尝试从召回池中找回被截断的上下文
        if enable_expansion:
            # 选取当前分数最高的作为种子
            seeds = ranked_items[:rerank_top_k]
            # 从原始召回池中寻找邻居
            ranked_items = self.expand_neighbors_from_pool(
                selected=seeds,
                pool=vector_hits, # 使用原始 hits 作为 pool
                neighbors=expansion_neighbors
            )

        # 5. 结果压缩 (Result Compression)
        # 合并同一文档中相邻的块，减少碎片化
        if enable_compression:
            ranked_items = self.compress_ranked_items(
                ranked_items,
                enable_compression=True
            )
        
        # 6. 最终截断
        return ranked_items[:rerank_top_k]