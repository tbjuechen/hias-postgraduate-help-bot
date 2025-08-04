# copy from https://github.com/langchain-ai/langchain/tree/master/libs/text-splitters
import re
from typing import List, Union, Literal, Callable


def _split_text_with_regex(
    text: str, separator: str, keep_separator: Union[bool, Literal["start", "end"]]
) -> List[str]:
    if separator:
        if keep_separator:
            _splits = re.split(f"({separator})", text)
            splits = (
                ([_splits[i] + _splits[i + 1] for i in range(0, len(_splits) - 1, 2)])
                if keep_separator == "end"
                else ([_splits[i] + _splits[i + 1] for i in range(1, len(_splits), 2)])
            )
            if len(_splits) % 2 == 0:
                splits += _splits[-1:]
            splits = (
                (splits + [_splits[-1]])
                if keep_separator == "end"
                else ([_splits[0]] + splits)
            )
        else:
            splits = re.split(separator, text)
    else:
        splits = list(text)
    return [s for s in splits if s != ""]


class RecursiveCharacterTextSplitter:
    def __init__(
        self,
        chunk_size: int = 4000,
        chunk_overlap: int = 200,
        length_function: Callable[[str], int] = len,
        keep_separator: Union[bool, Literal["start", "end"]] = True,
        separators: List[str] = None,
        is_separator_regex: bool = False,
        strip_whitespace: bool = True,
    ):
        if chunk_overlap > chunk_size:
            raise ValueError(
                f"Got a larger chunk overlap ({chunk_overlap}) than chunk size "
                f"({chunk_size}), should be smaller."
            )
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._length_function = length_function
        self._keep_separator = keep_separator
        self._separators = separators or ["\n\n", "\n", " ", ""]
        self._is_separator_regex = is_separator_regex
        self._strip_whitespace = strip_whitespace

    def _join_docs(self, docs: List[str], separator: str) -> str:
        text = separator.join(docs)
        if self._strip_whitespace:
            text = text.strip()
        return text if text else ""

    def _merge_splits(self, splits: List[str], separator: str) -> List[str]:
        separator_len = self._length_function(separator)
        docs = []
        current_doc: List[str] = []
        total = 0
        
        for d in splits:
            _len = self._length_function(d)
            if (
                total + _len + (separator_len if len(current_doc) > 0 else 0)
                > self._chunk_size
            ):
                if len(current_doc) > 0:
                    doc = self._join_docs(current_doc, separator)
                    if doc:
                        docs.append(doc)
                    
                    while total > self._chunk_overlap or (
                        total + _len + (separator_len if len(current_doc) > 0 else 0)
                        > self._chunk_size
                        and total > 0
                    ):
                        total -= self._length_function(current_doc[0]) + (
                            separator_len if len(current_doc) > 1 else 0
                        )
                        current_doc = current_doc[1:]
            
            current_doc.append(d)
            total += _len + (separator_len if len(current_doc) > 1 else 0)
        
        doc = self._join_docs(current_doc, separator)
        if doc:
            docs.append(doc)
        return docs

    def _split_text(self, text: str, separators: List[str]) -> List[str]:
        final_chunks = []
        separator = separators[-1]
        new_separators = []
        
        for i, _s in enumerate(separators):
            _separator = _s if self._is_separator_regex else re.escape(_s)
            if _s == "":
                separator = _s
                break
            if re.search(_separator, text):
                separator = _s
                new_separators = separators[i + 1 :]
                break

        _separator = separator if self._is_separator_regex else re.escape(separator)
        splits = _split_text_with_regex(text, _separator, self._keep_separator)

        _good_splits = []
        _separator = "" if self._keep_separator else separator
        
        for s in splits:
            if self._length_function(s) < self._chunk_size:
                _good_splits.append(s)
            else:
                if _good_splits:
                    merged_text = self._merge_splits(_good_splits, _separator)
                    final_chunks.extend(merged_text)
                    _good_splits = []
                if not new_separators:
                    final_chunks.append(s)
                else:
                    other_info = self._split_text(s, new_separators)
                    final_chunks.extend(other_info)
        
        if _good_splits:
            merged_text = self._merge_splits(_good_splits, _separator)
            final_chunks.extend(merged_text)
        return final_chunks

    def split_text(self, text: str) -> List[str]:
        return self._split_text(text, self._separators)

    def create_documents(self, texts: List[str]) -> List[str]:
        documents = []
        for text in texts:
            for chunk in self.split_text(text):
                documents.append(chunk)
        return documents