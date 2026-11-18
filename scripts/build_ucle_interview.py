"""Build the standalone Ucle practice page from reviewed answers and the supplied source."""
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / 'applications' / 'ucle-interview'


def bold(text):
    return re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html.escape(text))


def load_questions():
    category = None
    questions = []
    for line in (SITE / 'source.md').read_text().splitlines():
        match = re.match(r'## 분야 (\d+)\. (.+?) \(', line)
        if match:
            category = (int(match[1]), match[2])
        match = re.match(r'\*\*(\d+)\.\*\* (.+)', line)
        if match:
            if category is None:
                raise ValueError('Question without category')
            questions.append(dict(id=int(match[1]), question=match[2], category=category[0], category_name=category[1]))
    if [q['id'] for q in questions] != list(range(1, 201)):
        raise ValueError('Expected exactly the original questions 1–200')
    return questions


def build():
    questions = load_questions()
    answers = []
    for filename in ('answers-001-070.json', 'answers-071-140.json', 'answers-141-200.json'):
        answers.extend(json.loads((SITE / filename).read_text()))
    if [a['id'] for a in answers] != list(range(1, 201)):
        raise ValueError('Answers must cover 1–200 exactly once in order')
    cards, markdown = [], ['# 유클 CTO 커피챗 · 쉬운 답변 200문항\n']
    for question, answer in zip(questions, answers):
        if not (len(answer['keywords']) == 3 and 3 <= len(answer['answer']) <= 5):
            raise ValueError(f'Invalid answer structure: {answer["id"]}')
        for field in ('summary', 'explanation'):
            if not answer[field].strip() or '**' not in answer[field]:
                raise ValueError(f'Missing emphasis: {answer["id"]} {field}')
        if not all(isinstance(p, str) and '**' in p for p in answer['answer']):
            raise ValueError(f'Missing paragraph emphasis: {answer["id"]}')
        qid = question['id']
        keywords = ''.join(f'<strong>{html.escape(k)}</strong>' for k in answer['keywords'])
        paragraphs = ''.join(f'<p>{bold(p)}</p>' for p in answer['answer'])
        caution = f'<p class="caution">{bold(answer["caution"])}</p>' if answer.get('caution') else ''
        label = '이렇게 물어보세요' if qid >= 191 else '이렇게 말해보세요'
        cards.append(f'''<article class="card" id="question-{qid}" data-id="{qid}" data-category="{question['category']}">
<p class="category">{html.escape(question['category_name'])} · {qid}번</p>
<h2 tabindex="-1">{bold(question['question'])}</h2>
<div class="answer-step" data-step="1"><h3>한 줄 핵심</h3><p>{bold(answer['summary'])}</p><div class="keywords">{keywords}</div></div>
<div class="answer-step spoken" data-step="2"><h3>{label}</h3>{paragraphs}{caution}</div>
<div class="answer-step" data-step="3"><h3>쉽게 이해하기</h3><p>{bold(answer['explanation'])}</p></div>
</article>''')
        markdown.extend([f'## {qid}. {question["question"]}\n', answer['summary'], '\n**기억할 키워드:** ' + ' · '.join(f'**{k}**' for k in answer['keywords']), '\n### ' + label, '\n\n'.join(answer['answer']), '\n### 쉽게 이해하기', answer['explanation'], caution and '\n> ' + answer['caution'], '\n'])
    categories = {q['category']: q['category_name'] for q in questions}
    options = ''.join(f'<option value="{i}">{html.escape(name)}</option>' for i, name in categories.items())
    template = (SITE / 'template.html').read_text()
    (SITE / 'index.html').write_text(template.replace('@@CARDS@@', '\n'.join(cards)).replace('@@OPTIONS@@', options))
    (SITE / 'answers.md').write_text('\n'.join(markdown).rstrip() + '\n')
    print(f'Built {len(cards)} questions in {len(categories)} categories')


if __name__ == '__main__':
    build()
