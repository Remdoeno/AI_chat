"""Conservative detection of a model splitting an explicitly staged plan."""
import re


def needs_project_repair(message, decision):
    if not isinstance(decision, dict) or not isinstance(decision.get('operations'), list):
        return False  # The main response validator reports malformed JSON.
    entries = [op.get('event', {}) for op in decision['operations']
               if isinstance(op, dict) and op.get('action') == 'create' and isinstance(op.get('event'), dict)]
    if len(entries) < 2 or any(e.get('kind') == 'project' for e in entries):
        return False
    if not re.search(r'阶段|节点|长期|论文|项目|旅行|筹备', message, re.I):
        return False
    if re.search(r'阶段|节点|长期', message):
        return True
    if not re.search(r'先|然后|最后|再|接着', message):
        return False
    titles = [str(e.get('title', '')).lower() for e in entries]
    # A shared four-character subject (e.g. Fire) is stronger than dates alone.
    return any(any(title[j:j+4] in other for other in titles[i+1:])
               for i, title in enumerate(titles) for j in range(max(0, len(title)-3)))
