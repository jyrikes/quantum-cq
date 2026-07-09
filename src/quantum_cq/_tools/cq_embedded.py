#@title Biblioteca CQ embutida { display-mode: "form" }
# Fonte: notebooks/cq.py. Esta célula torna o notebook autossuficiente no Google Colab.
_CQ_EMBUTIDA = True

# Versao compacta funcional da biblioteca CQ (gerada a partir da celula 1)
import ast
from dataclasses import dataclass, field
from html import escape
from types import SimpleNamespace
import base64
import contextlib
import io
import json
import re
import sys
import traceback
import uuid
from typing import Any, cast


def _require_ipython_display():
    try:
        from IPython.display import HTML as ipython_html
        from IPython.display import display as ipython_display
    except ImportError as exc:
        raise ImportError(
            "Para usar quantum_cq.cq_embedded, instale quantum-cq[notebook]."
        ) from exc

    return ipython_html, ipython_display


def HTML(*args, **kwargs):
    html_cls, _ = _require_ipython_display()
    return html_cls(*args, **kwargs)


def display(*args, **kwargs):
    _, display_fn = _require_ipython_display()
    return display_fn(*args, **kwargs)


try:
    from IPython.utils.capture import capture_output
except Exception:
    capture_output = None

try:
    from IPython.core.interactiveshell import InteractiveShell
except Exception:
    InteractiveShell = None


def _render_lines(text):
    text = (text or "").strip()
    if not text:
        return ""
    return "<br>".join(escape(part) for part in text.splitlines())


def _encode_image(data):
    if not data:
        return ""
    if isinstance(data, bytes):
        raw = data
    else:
        raw = data.encode("utf-8") if isinstance(data, str) else bytes(data)
    return base64.b64encode(raw).decode("ascii")


def _bundle_value(value):
    if isinstance(value, (list, tuple)):
        return "".join(str(part) for part in value)
    return value


def _bundle_from_object(obj):
    bundle = {}
    metadata = {}

    if isinstance(obj, dict) and "data" in obj:
        metadata = obj.get("metadata") or {}
        data = obj.get("data") or {}
        if isinstance(data, dict):
            bundle = {key: _bundle_value(value) for key, value in data.items() if value is not None}

    if not bundle and InteractiveShell is not None:
        try:
            shell = cast(Any, InteractiveShell).instance()
            data, metadata = shell.display_formatter.format(obj)
            if isinstance(data, dict):
                bundle = {key: _bundle_value(value) for key, value in data.items() if value is not None}
                metadata = metadata or {}
        except Exception:
            bundle = {}
            metadata = {}

    repr_mimebundle = getattr(obj, "_repr_mimebundle_", None)
    if not bundle and callable(repr_mimebundle):
        try:
            mime = repr_mimebundle()
            if isinstance(mime, tuple):
                data, metadata = mime
            else:
                data = mime
            if isinstance(data, dict):
                bundle = {key: _bundle_value(value) for key, value in data.items() if value is not None}
                metadata = metadata or {}
        except Exception:
            bundle = {}
            metadata = {}

    if not bundle or ("text/plain" in bundle and len(bundle) == 1):
        try:
            from matplotlib.figure import Figure
            if isinstance(obj, Figure):
                image = io.BytesIO()
                obj.savefig(image, format="png", bbox_inches="tight")
                bundle["image/png"] = base64.b64encode(image.getvalue()).decode("ascii")
        except Exception:
            pass

    if not bundle:
        for attr, mime in (
            ("_repr_html_", "text/html"),
            ("_repr_svg_", "image/svg+xml"),
            ("_repr_png_", "image/png"),
            ("_repr_jpeg_", "image/jpeg"),
            ("_repr_markdown_", "text/markdown"),
            ("_repr_json_", "application/json"),
        ):
            if hasattr(obj, attr):
                try:
                    value = getattr(obj, attr)()
                except Exception:
                    value = None
                if value is not None:
                    bundle[mime] = _bundle_value(value)
                    break

    if "text/plain" not in bundle:
        bundle["text/plain"] = repr(obj)

    return bundle, metadata


def _patched_display_factory(record_output):
    def _patched_display(*objs, **kwargs):
        if not objs:
            return None
        for obj in objs:
            bundle, metadata = _bundle_from_object(obj)
            record_output({
                "output_type": "display_data",
                "data": bundle,
                "metadata": metadata or {},
            })
        return None
    return _patched_display


def _run_python(code, namespace=None):
    ns = {"__name__": "__cq_exec__", "__builtins__": __builtins__}
    if namespace:
        ns.update(namespace)
    stdout = ""
    stderr = ""
    outputs = []
    error = ""
    patched = []

    def record_output(output):
        outputs.append(output)

    ns.setdefault("display", _patched_display_factory(record_output))
    ns.setdefault("HTML", HTML)

    try:
        shell_modules = (
            "IPython.display",
            "IPython.core.display",
            "IPython.core.display_functions",
        )
        for module_name in shell_modules:
            module = sys.modules.get(module_name)
            if module is not None and hasattr(module, "display"):
                patched.append((module, getattr(module, "display")))
                setattr(module, "display", _patched_display_factory(record_output))

        tree = ast.parse(code or "", mode="exec")
        body = list(tree.body)
        tail = None
        if body and isinstance(body[-1], ast.Expr):
            expr = cast(ast.Expr, body.pop())
            tail = expr.value

        out = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            if body:
                exec(compile(ast.Module(body=body, type_ignores=[]), "<cq execucao>", "exec"), ns, ns)
            if tail is not None:
                result = eval(compile(ast.Expression(tail), "<cq execucao>", "eval"), ns, ns)
                if result is not None:
                    bundle, metadata = _bundle_from_object(result)
                    record_output({
                        "output_type": "execute_result",
                        "data": bundle,
                        "metadata": metadata or {},
                        "execution_count": None,
                    })
        stdout = out.getvalue()
        stderr = err.getvalue()
    except Exception:
        error = traceback.format_exc()
    finally:
        for module, original in patched:
            setattr(module, "display", original)

    return SimpleNamespace(namespace=ns, stdout=stdout, stderr=stderr, outputs=outputs, error=error)


def _run_python_live(code, namespace=None):
    ns = {"__name__": "__cq_exec__", "__builtins__": __builtins__, "HTML": HTML, "display": display}
    if namespace:
        ns.update(namespace)

    tree = ast.parse(code or "", mode="exec")
    body = list(tree.body)
    tail = None
    if body and isinstance(body[-1], ast.Expr):
        expr = cast(ast.Expr, body.pop())
        tail = expr.value

    if body:
        exec(compile(ast.Module(body=body, type_ignores=[]), "<cq execucao>", "exec"), ns, ns)
    if tail is not None:
        result = eval(compile(ast.Expression(tail), "<cq execucao>", "eval"), ns, ns)
        if result is not None:
            display(result)
    return ns


def _rich_output_html(item):
    if isinstance(item, dict):
        output_type = item.get("output_type", "")
        data = item.get("data", {})
        text = item.get("text", "")
        ename = item.get("ename", "")
        evalue = item.get("evalue", "")
    else:
        output_type = getattr(item, "output_type", "")
        data = getattr(item, "data", {}) or {}
        text = getattr(item, "text", "")
        ename = getattr(item, "ename", "")
        evalue = getattr(item, "evalue", "")

    if output_type == "error" or ename:
        body = text or "\n".join([ename, evalue])
        return f"<pre style='margin:0;background:#3f1d1d;color:#fecaca;border:1px solid #ef4444;padding:12px;border-radius:10px;overflow:auto;white-space:pre-wrap;'>{escape(body)}</pre>"

    if "text/html" in data:
        return f"<div style='overflow:auto'>{data['text/html']}</div>"

    if "image/svg+xml" in data:
        return f"<div style='overflow:auto'>{data['image/svg+xml']}</div>"

    if "image/png" in data:
        img = data["image/png"]
        if isinstance(img, str):
            payload = img
        else:
            payload = _encode_image(img)
        return f"<div style='overflow:auto'><img alt='saida' style='max-width:100%;height:auto' src='data:image/png;base64,{payload}'></div>"

    if "image/jpeg" in data:
        img = data["image/jpeg"]
        if isinstance(img, str):
            payload = img
        else:
            payload = _encode_image(img)
        return f"<div style='overflow:auto'><img alt='saida' style='max-width:100%;height:auto' src='data:image/jpeg;base64,{payload}'></div>"

    if "application/vnd.jupyter.widget-view+json" in data:
        widget = data["application/vnd.jupyter.widget-view+json"]
        plain = _bundle_value(data.get("text/plain", "Widget interativo"))
        widget_repr = json.dumps(widget, ensure_ascii=False, indent=2) if isinstance(widget, (dict, list)) else str(widget)
        return f"<div style='border:1px dashed #475569;background:#111827;color:#e2e8f0;padding:12px;border-radius:10px;overflow:auto;'><div style='font-weight:700;margin-bottom:6px;'>Widget interativo</div><div style='margin-bottom:8px;'>{escape(str(plain))}</div><pre style='margin:0;white-space:pre-wrap;'>{escape(widget_repr)}</pre></div>"

    if "text/markdown" in data:
        markdown = _bundle_value(data["text/markdown"])
        return f"<pre style='margin:0;background:#111827;color:#e2e8f0;border:1px solid #334155;padding:12px;border-radius:10px;overflow:auto;white-space:pre-wrap;'>{escape(str(markdown))}</pre>"

    if "text/plain" in data:
        plain = _bundle_value(data["text/plain"])
        return f"<pre style='margin:0;background:#111827;color:#e2e8f0;border:1px solid #334155;padding:12px;border-radius:10px;overflow:auto;white-space:pre-wrap;'>{escape(str(plain))}</pre>"

    if text:
        return f"<pre style='margin:0;background:#111827;color:#e2e8f0;border:1px solid #334155;padding:12px;border-radius:10px;overflow:auto;white-space:pre-wrap;'>{escape(str(text))}</pre>"

    return ""


def _render_exec_result(result):
    parts = []
    if result.stdout.strip():
        parts.append(f"<pre style='margin:0 0 10px 0;background:#111827;color:#e2e8f0;border:1px solid #334155;padding:12px;border-radius:10px;overflow:auto;white-space:pre-wrap;'>{escape(result.stdout)}</pre>")
    if result.stderr.strip():
        parts.append(f"<pre style='margin:0 0 10px 0;background:#3f1d1d;color:#fecaca;border:1px solid #ef4444;padding:12px;border-radius:10px;overflow:auto;white-space:pre-wrap;'>{escape(result.stderr)}</pre>")
    for item in getattr(result, "outputs", []) or []:
        html = _rich_output_html(item)
        if html:
            parts.append(html)
    if result.error:
        parts.append(f"<pre style='margin:0;background:#3f1d1d;color:#fecaca;border:1px solid #ef4444;padding:12px;border-radius:10px;overflow:auto;white-space:pre-wrap;'>{escape(result.error)}</pre>")
    return "".join(parts) or "<div style='color:#cfd6e7'>Sem saida.</div>"
@dataclass
class CQBlock:
    kind: str
    title: str
    content: str = ''
    items: list = field(default_factory=list)
@dataclass
class CQDoc:
    id: str = 'pagina'
    title: str = 'Página'
    subtitle: str = ''
    label: str = 'Módulo'
    theme: str = 'dark'
    mode: str = 'steps'
    previous: str = ''
    next: str = ''
    home: str = '#navegacao-rapida'
    numbered: bool = True
    export: bool = True
    report: bool = True
    blocks: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    errors: list = field(default_factory=list)
class CQStyle:
    SPACE = {'zero': '0', 'xs': '4px', 'sm': '8px', 'md': '14px', 'lg': '22px', 'xl': '32px', 'xxl': '48px'}
    SIZE = {'xs': '12px', 'sm': '14px', 'md': '16px', 'lg': '20px', 'xl': '28px', 'xxl': '36px'}
    ALIGN = {'esquerda': 'left', 'centro': 'center', 'direita': 'right', 'justificado': 'justify'}
    @classmethod
    def val(cls, v, table=None):
        if isinstance(v, (int, float)):
            return f'{v}px'
        return (table or {}).get(str(v), str(v))
    @classmethod
    def style(cls, **kw):
        rules = {'m': lambda v: f'margin:{cls.val(v, cls.SPACE)};', 'mt': lambda v: f'margin-top:{cls.val(v, cls.SPACE)};', 'mb': lambda v: f'margin-bottom:{cls.val(v, cls.SPACE)};', 'p': lambda v: f'padding:{cls.val(v, cls.SPACE)};', 'pt': lambda v: f'padding-top:{cls.val(v, cls.SPACE)};', 'pb': lambda v: f'padding-bottom:{cls.val(v, cls.SPACE)};', 'w': lambda v: f"width:{('100%' if v in ['full', 'cheio'] else cls.val(v))};", 'h': lambda v: f'height:{cls.val(v)};', 'font': lambda v: f'font-size:{cls.val(v, cls.SIZE)};', 'align': lambda v: f'text-align:{cls.ALIGN.get(str(v), v)};', 'color': lambda v: f'color:{v};', 'bg': lambda v: f'background:{v};', 'radius': lambda v: f'border-radius:{cls.val(v, cls.SPACE)};', 'border': lambda v: f'border:{v};', 'display': lambda v: f'display:{v};', 'gap': lambda v: f'gap:{cls.val(v, cls.SPACE)};'}
        return ' '.join((rules[k](v) for k, v in kw.items() if k in rules and v is not None))
    @classmethod
    def box(cls, content='', **kw):
        return f"<div style='{escape(cls.style(**kw))}'>{content}</div>"
class CQUtil:
    @staticmethod
    def slug(text):
        text = text.strip().lower()
        repl = {'[áàãâä]': 'a', '[éèêë]': 'e', '[íìîï]': 'i', '[óòõôö]': 'o', '[úùûü]': 'u', '[ç]': 'c'}
        for a, b in repl.items():
            text = re.sub(a, b, text)
        return re.sub('[^a-z0-9]+', '-', text).strip('-') or 'pagina'
    @staticmethod
    def href(value):
        value = value.strip()
        return value if value.startswith('#') else f'#{value}' if value else ''
    @staticmethod
    def yes(value):
        return value.strip().lower() not in {'nao', 'não', 'false', '0', 'off'}
    @staticmethod
    def lines(content):
        result = []
        for line in content.splitlines():
            line = line.strip()
            line = re.sub('^[-*]\\s+', '', line)
            line = re.sub('^\\d+\\.\\s+', '', line)
            if line:
                result.append(line)
        return result
    @staticmethod
    def chunks(content, marker='---'):
        parts = []
        current = []
        for raw in (content or '').splitlines():
            line = raw.rstrip()
            if line.strip() == marker:
                chunk = '\n'.join(current).strip()
                if chunk:
                    parts.append(chunk)
                current = []
            else:
                current.append(line)
        chunk = '\n'.join(current).strip()
        if chunk:
            parts.append(chunk)
        return parts
    @staticmethod
    def cover_fields(content):
        fields = {'meta': [], 'nav': [], 'roadmap': [], 'objective': '', 'title': '', 'subtitle': '', 'logo': '', 'institution': '', 'school': '', 'author': '', 'course': '', 'teacher': ''}
        current = None
        for raw in (content or '').splitlines():
            line = raw.strip()
            if not line:
                continue
            lower = line.lower().rstrip(':')
            if lower in {'navegação rápida', 'navegacao rapida', 'navegacao', 'nav'}:
                current = 'nav'
                continue
            if lower in {'roteiro', 'sumario', 'sumário'}:
                current = 'roadmap'
                continue
            if lower in {'metadados', 'dados', 'meta'}:
                current = 'meta'
                continue
            if ':' in line:
                key, value = line.split(':', 1)
                key = CQUtil.slug(key).replace('-', '_')
                value = value.strip()
                mapping = {
                    'titulo': 'title',
                    'title': 'title',
                    'subtitulo': 'subtitle',
                    'subtitle': 'subtitle',
                    'logo': 'logo',
                    'objetivo': 'objective',
                    'objective': 'objective',
                    'instituicao': 'institution',
                    'instituição': 'institution',
                    'institution': 'institution',
                    'unidade': 'school',
                    'school': 'school',
                    'aluno': 'author',
                    'autor': 'author',
                    'author': 'author',
                    'disciplina': 'course',
                    'course': 'course',
                    'professor': 'teacher',
                    'teacher': 'teacher',
                }
                key = mapping.get(key, key)
                if key in {'nav', 'roadmap', 'meta'}:
                    current = key
                    if value:
                        fields[key].append(value)
                    continue
                if key in fields and isinstance(fields[key], str):
                    fields[key] = value
                    continue
                fields.setdefault(key, value)
                if value:
                    current = None
                continue
            if line.startswith(('-', '*')):
                item = re.sub(r'^[-*]\\s*', '', line).strip()
                if current in {'nav', 'roadmap', 'meta'}:
                    fields[current].append(item)
                continue
            if current in {'nav', 'roadmap', 'meta'}:
                fields[current].append(line)
            elif not fields['objective']:
                fields['objective'] = line
            else:
                fields.setdefault('body', []).append(line)
        return fields
class CQRegistry:
    TITLES = {'objetivo': 'Objetivo', 'passo': 'Passo', 'bloco': 'Conteúdo', 'aviso': 'Aviso', 'dica': 'Dica', 'pergunta': 'Pergunta', 'reflexao': 'Reflexão', 'checklist': 'Checklist', 'quiz': 'Quiz', 'resposta': 'Resposta do aluno', 'codigo': 'Código', 'execucao': 'Execução', 'interativo': 'Interativo', 'layout': 'Layout', 'capa': 'Capa', 'formula': 'Fórmula', 'circuito': 'Circuito quântico', 'histograma': 'Histograma', 'oraculo': 'Oráculo', 'medicao': 'Medição', 'comparacao': 'Comparação clássica/quântica'}
    COLORS = {'objetivo': '#cfd6e7', 'passo': '#94a3b8', 'bloco': '#94a3b8', 'aviso': '#facc15', 'dica': '#86efac', 'pergunta': '#93c5fd', 'reflexao': '#93c5fd', 'checklist': '#cfd6e7', 'quiz': '#f0abfc', 'resposta': '#a7f3d0', 'codigo': '#c4b5fd', 'execucao': '#93c5fd', 'interativo': '#67e8f9', 'layout': '#cfd6e7', 'capa': '#cfd6e7', 'formula': '#67e8f9', 'circuito': '#a78bfa', 'histograma': '#60a5fa', 'oraculo': '#fb7185', 'medicao': '#34d399', 'comparacao': '#fbbf24'}
    THEMES = {'dark': {'bg': '#0f172a', 'panel': '#1e293b', 'panel2': '#334155', 'text': '#f8fafc', 'muted': '#cfd6e7', 'soft': '#e2e8f0', 'primary': '#cfd6e7', 'primary_text': '#0f172a', 'border': '#334155'}, 'quantum': {'bg': '#111827', 'panel': '#1f2937', 'panel2': '#374151', 'text': '#f9fafb', 'muted': '#d1d5db', 'soft': '#e5e7eb', 'primary': '#a78bfa', 'primary_text': '#111827', 'border': '#4b5563'}, 'light': {'bg': '#f8fafc', 'panel': '#ffffff', 'panel2': '#e2e8f0', 'text': '#0f172a', 'muted': '#475569', 'soft': '#334155', 'primary': '#0f172a', 'primary_text': '#ffffff', 'border': '#cbd5e1'}}
    @classmethod
    def title(cls, kind):
        return cls.TITLES.get(kind, kind.title())
    @classmethod
    def color(cls, kind):
        return cls.COLORS.get(kind, '#cfd6e7')
    @classmethod
    def theme(cls, name):
        if isinstance(name, dict):
            return name
        return cls.THEMES.get(name, cls.THEMES['dark'])
class CQValidator:
    @staticmethod
    def validate(doc: CQDoc):
        has_cover = any(block.kind == 'capa' for block in doc.blocks)
        if (not doc.title or doc.title == 'Página') and not has_cover:
            doc.warnings.append('Nenhum @titulo definido.')
        if not doc.blocks:
            doc.errors.append('Nenhum bloco de conteúdo definido.')
        if not doc.previous:
            doc.warnings.append('Nenhum @anterior definido.')
        if not doc.next:
            doc.warnings.append('Nenhum @proximo definido.')
class CQParser:
    HANDLERS = {}
    @classmethod
    def command(cls, *names):
        def decorator(fn):
            for name in names:
                cls.HANDLERS[name] = fn
            return fn
        return decorator
    @classmethod
    def parse(cls, source: str) -> CQDoc:
        doc = CQDoc()
        command = None
        buffer = []
        def flush():
            nonlocal command, buffer
            if not command:
                buffer = []
                return
            content = '\n'.join(buffer).strip()
            handler = cls.HANDLERS.get(command, cls.block)
            handler(doc, command, content)
            buffer = []
        for raw in source.strip().splitlines():
            line = raw.rstrip()
            if line.strip().startswith('@'):
                flush()
                command = line.strip()[1:].strip().lower()
            else:
                buffer.append(line)
        flush()
        doc.id = doc.id or CQUtil.slug(doc.title)
        CQValidator.validate(doc)
        return doc
    @staticmethod
    def block(doc, command, content):
        command_name = str(command)
        title = str(CQRegistry.title(command_name) or command_name)
        doc.blocks.append(CQBlock(command_name, title, content))
@CQParser.command('pagina', 'id')
def _(doc, cmd, content):
    doc.id = CQUtil.slug(content)
@CQParser.command('titulo')
def _(doc, cmd, content):
    doc.title = content or doc.title
@CQParser.command('subtitulo')
def _(doc, cmd, content):
    doc.subtitle = content
@CQParser.command('tipo', 'etiqueta')
def _(doc, cmd, content):
    doc.label = content or doc.label
@CQParser.command('tema')
def _(doc, cmd, content):
    doc.theme = CQUtil.slug(content or 'dark')
@CQParser.command('modo')
def _(doc, cmd, content):
    doc.mode = CQUtil.slug(content or 'steps')
@CQParser.command('anterior')
def _(doc, cmd, content):
    doc.previous = CQUtil.href(content)
@CQParser.command('proximo')
def _(doc, cmd, content):
    doc.next = CQUtil.href(content)
@CQParser.command('inicio')
def _(doc, cmd, content):
    doc.home = CQUtil.href(content) or '#navegacao-rapida'
@CQParser.command('numeracao')
def _(doc, cmd, content):
    doc.numbered = CQUtil.yes(content)
@CQParser.command('exportar')
def _(doc, cmd, content):
    doc.export = CQUtil.yes(content)
@CQParser.command('relatorio')
def _(doc, cmd, content):
    doc.report = CQUtil.yes(content)
@CQParser.command('checklist')
def _(doc, cmd, content):
    doc.blocks.append(CQBlock('checklist', 'Checklist', items=CQUtil.lines(content)))
@CQParser.command('quiz')
def _(doc, cmd, content):
    doc.blocks.append(CQBlock('quiz', 'Quiz', content))
@CQParser.command('resposta')
def _(doc, cmd, content):
    doc.blocks.append(CQBlock('resposta', 'Resposta do aluno', content))
@CQParser.command('codigo')
def _(doc, cmd, content):
    doc.blocks.append(CQBlock('codigo', 'Código', content))
@CQParser.command('execucao')
def _(doc, cmd, content):
    doc.blocks.append(CQBlock('execucao', 'Execução', content))
@CQParser.command('interativo')
def _(doc, cmd, content):
    doc.blocks.append(CQBlock('interativo', 'Interativo', content))
@CQParser.command('formula')
def _(doc, cmd, content):
    doc.blocks.append(CQBlock('formula', 'Fórmula', content))
@CQParser.command('comparacao')
def _(doc, cmd, content):
    doc.blocks.append(CQBlock('comparacao', 'Comparação clássica/quântica', content))
@CQParser.command('layout')
def _(doc, cmd, content):
    doc.blocks.append(CQBlock('layout', 'Layout', content))
@CQParser.command('capa')
def _(doc, cmd, content):
    fields = CQUtil.cover_fields(content)
    if fields.get('title'):
        doc.title = fields['title']
    if fields.get('subtitle'):
        doc.subtitle = fields['subtitle']
    doc.blocks.append(CQBlock('capa', 'Capa', content))
@CQParser.command('objetivo', 'passo', 'bloco', 'aviso', 'dica', 'pergunta', 'reflexao', 'circuito', 'histograma', 'oraculo', 'medicao')
def _(doc, cmd, content):
    CQParser.block(doc, cmd, content)
class CQRenderer:
    HANDLERS = {}
    @classmethod
    def handler(cls, *kinds):
        def decorator(fn):
            for kind in kinds:
                cls.HANDLERS[kind] = fn
            return fn
        return decorator
    @classmethod
    def render(cls, doc: CQDoc, standalone: bool=False) -> str:
        uid = 'cq_' + uuid.uuid4().hex[:10]
        theme = CQRegistry.theme(doc.theme)
        blocks_html = '\n'.join((cls.block(doc, b, i, theme) for i, b in enumerate(doc.blocks)))
        total = max(len(doc.blocks), 1)
        html = f'''\n<a id="{escape(doc.id)}"></a>\n<div id="{uid}" class="cq-page" data-page="{escape(doc.id)}">\n<style>{cls.css(uid, theme)}</style>\n\n<div class="cq-shell">\n  {cls.warnings(doc)}\n  <div class="cq-label">{escape(doc.label)}</div>\n  <h1>{escape(doc.title)}</h1>\n  <h3>{escape(doc.subtitle)}</h3>\n\n  <div class="cq-progress"><div class="cq-progress-fill"></div></div>\n  <div class="cq-counter">Bloco 1 de {total}</div>\n\n  <div class="cq-blocks">{blocks_html}</div>\n\n  <div class="cq-controls">\n    <button class="cq-prev">← Anterior</button>\n    <button class="cq-next">Próximo →</button>\n    <button class="cq-show">Mostrar tudo</button>\n    <button class="cq-reset">Reiniciar</button>\n    {("<button class='cq-export'>Exportar HTML</button>" if doc.export else '')}\n    {("<button class='cq-report'>Relatório final</button>" if doc.report else '')}\n  </div>\n\n  <div class="cq-nav">\n    <a href="{escape(doc.home)}">⬆ Voltar ao início</a>\n    {(f'<a href="{escape(doc.previous)}">← Módulo anterior</a>' if doc.previous else '')}\n    {(f'<a class="primary" href="{escape(doc.next)}">Próximo módulo →</a>' if doc.next else '')}\n  </div>\n</div>\n\n<script>{cls.js(uid, doc.id)}</script>\n</div>\n'''
        return f"<!doctype html><html><head><meta charset='utf-8'></head><body>{html}</body></html>" if standalone else html
    @classmethod
    def block(cls, doc: CQDoc, block: CQBlock, index: int, theme):
        renderer = cls.HANDLERS.get(block.kind, cls.text)
        return renderer(doc, block, index, theme)
    @classmethod
    def text(cls, doc, block, index, theme):
        body = []
        if block.content.strip():
            body.append('<p>' + escape(block.content).replace('\n', '<br>') + '</p>')
        if block.items:
            body.append('<ul>' + ''.join((f'<li>{escape(item)}</li>' for item in block.items)) + '</ul>')
        return cls.shell(doc, block, index, ''.join(body) or '&nbsp;')
    @staticmethod
    def code_html(code, language='python'):
        code = (code or '').rstrip()
        return f"""
<div style="border:1px solid #334155;border-radius:12px;overflow:hidden;background:#0f172a;color:#f8fafc;">
  <div style="display:flex;align-items:center;justify-content:space-between;padding:10px 14px;background:#111827;border-bottom:1px solid #334155;">
    <span style="font-size:12px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:#cfd6e7;">{escape(language)}</span>
  </div>
  <pre style="margin:0;padding:14px;overflow:auto;background:#0f172a;color:#f8fafc;font-family:Consolas, 'Courier New', monospace;font-size:13px;line-height:1.5;"><code>{escape(code)}</code></pre>
</div>
"""
    @staticmethod
    def layout_html(content):
        parts = CQUtil.chunks(content, marker='---') or [content]
        if len(parts) == 1:
            return f"<div style='display:block'>{_render_lines(parts[0])}</div>"
        cols = ''.join(
            f"<div style='min-width:0;padding:14px;border:1px solid #334155;border-radius:12px;background:#1e293b;color:#f8fafc;'>{_render_lines(part)}</div>"
            for part in parts
        )
        return f"<div style='display:grid;grid-template-columns:repeat({len(parts)}, minmax(0, 1fr));gap:14px;'>{cols}</div>"
    @staticmethod
    def execucao_html(code, title='Execução', language='python', interactive=False, namespace=None):
        result = _run_python(code, namespace=namespace)
        note = "Interativo em Python" if interactive else "Saída da execução"
        content = f"""
<div style="border:1px solid #334155;border-radius:12px;overflow:hidden;background:#0f172a;color:#f8fafc;">
  <div style="display:flex;align-items:center;justify-content:space-between;padding:10px 14px;background:#111827;border-bottom:1px solid #334155;">
    <span style="font-size:12px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:#cfd6e7;">{escape(title)}</span>
    <span style="font-size:12px;color:#cfd6e7;">{escape(note)}</span>
  </div>
  <div style="border-bottom:1px solid #334155;">{CQRenderer.code_html(code, language=language)}</div>
  <div style="padding:14px;">
    { _render_exec_result(result) }
  </div>
</div>
"""
        return content
    @staticmethod
    def cover_html(title, subtitle='', logo='', objective='', meta=None, nav=None, roadmap=None, anchor='navegacao-rapida', theme='dark'):
        t = CQRegistry.theme(theme)
        meta = meta or []
        nav = nav or []
        roadmap = roadmap or []
        left_meta = ''.join(
            f"<tr><td style='color:{t['muted']};border-bottom:1px solid {t['border']};padding:8px 12px 8px 0;white-space:nowrap;'>{escape(str(k))}</td><td style='border-bottom:1px solid {t['border']};padding:8px 0;'>{escape(str(v))}</td></tr>"
            for k, v in meta
        )
        nav_html = ''.join(
            f"<a href='{escape(href)}' style='display:block;color:{t['text']};text-decoration:none;padding:9px 0;border-bottom:1px solid {t['border']};'>{escape(label)}</a>"
            for label, href in nav
        )
        roadmap_html = ''.join(f"<li style='margin:0.25rem 0;'>{escape(item)}</li>" for item in roadmap)
        objective_html = f"<div style='margin-top:22px;padding:14px;border-left:4px solid {t['primary']};background:{t['panel']};border-radius:10px;color:{t['soft']};line-height:1.55;'><b style='color:{t['text']}'>Objetivo:</b> {escape(objective)}</div>" if objective else ''
        logo_html = f"<img src='{escape(logo)}' alt='' width='190' style='max-width:100%;height:auto;'>" if logo else ''
        left_meta_html = f"<table width='100%' cellpadding='8' cellspacing='0' style='margin-top:20px;color:{t['text']};border-collapse:collapse;'>{left_meta}</table>" if left_meta else ''
        roadmap_block = f"<div style='margin-top:24px;padding-top:16px;border-top:1px solid {t['border']};'><div style='color:{t['muted']};font-size:12px;font-weight:700;letter-spacing:1px;text-transform:uppercase;margin-bottom:10px;'>Roteiro</div><ol style='margin:0;padding-left:20px;color:{t['soft']};line-height:1.65;font-size:14px;'>{roadmap_html}</ol></div>" if roadmap_html else ''
        nav_block = f"<div style='margin-top:24px;padding-top:16px;border-top:1px solid {t['border']};'><div style='color:{t['muted']};font-size:12px;font-weight:700;letter-spacing:1px;text-transform:uppercase;margin-bottom:12px;'>Navegação rápida</div>{nav_html}</div>" if nav_html else ''
        return f"""
<a id="{escape(anchor)}"></a>
<div style="background:{t['bg']};color:{t['text']};border-radius:18px;padding:24px;font-family:Arial, Helvetica, sans-serif;">
  <div style="display:grid;grid-template-columns:minmax(0, 56%) minmax(0, 44%);gap:0;border:1px solid {t['border']};border-radius:18px;overflow:hidden;background:{t['bg']};">
    <div style="padding:20px 20px 20px 20px;">
      <div style="text-align:center;">
        {logo_html}
        <h1 style="color:{t['text']};margin:22px 0 8px 0;">{escape(title)}</h1>
        <h3 style="color:{t['muted']};margin:0 0 14px 0;">{escape(subtitle)}</h3>
      </div>
      {objective_html}
      {left_meta_html}
    </div>
    <div style="padding:20px;border-left:1px solid {t['border']};">
      {nav_block}
      {roadmap_block}
    </div>
  </div>
</div>
"""
    @classmethod
    def shell(cls, doc, block, index, content):
        title = f'{index + 1}. {block.title}' if doc.numbered else block.title
        accent = CQRegistry.color(block.kind)
        return f'\n<section id="{escape(doc.id)}-bloco-{index + 1}" class="cq-step" data-step="{index}">\n  <div class="cq-card" style="border-left-color:{accent}">\n    <div class="cq-card-title" style="color:{accent}">{escape(title)}</div>\n    <div class="cq-card-body">{content}</div>\n  </div>\n</section>\n'
    @classmethod
    def warnings(cls, doc):
        items = doc.errors + doc.warnings
        if not items:
            return ''
        lis = ''.join((f'<li>{escape(x)}</li>' for x in items))
        return f"<div class='cq-warn'><b>Avisos:</b><ul>{lis}</ul></div>"
    @staticmethod
    def css(uid, t):
        return f"\n#{uid} .cq-shell {{\n  background:{t['bg']}; color:{t['text']}; border-radius:18px;\n  padding:24px; font-family:Arial, Helvetica, sans-serif;\n}}\n#{uid} h1 {{ margin:0 0 8px 0; color:{t['text']}; }}\n#{uid} h3 {{ margin:0 0 18px 0; color:{t['muted']}; }}\n#{uid} .cq-label {{\n  color:{t['muted']}; font-size:12px; font-weight:bold;\n  letter-spacing:1px; text-transform:uppercase; margin-bottom:10px;\n}}\n#{uid} .cq-progress {{ height:10px; background:{t['panel2']}; border-radius:999px; overflow:hidden; margin-top:18px; }}\n#{uid} .cq-progress-fill {{ width:0%; height:100%; background:{t['primary']}; transition:.25s; }}\n#{uid} .cq-counter {{ color:{t['muted']}; font-size:13px; margin-top:8px; }}\n#{uid} .cq-step {{ display:none; margin-top:14px; }}\n#{uid} .cq-card {{ background:{t['panel']}; border-left:4px solid {t['primary']}; border-radius:12px; padding:16px; }}\n#{uid} .cq-card-title {{ font-size:12px; font-weight:bold; letter-spacing:1px; text-transform:uppercase; margin-bottom:10px; }}\n#{uid} .cq-card-body {{ color:{t['soft']}; font-size:15px; line-height:1.7; }}\n#{uid} .cq-card-body p {{ margin:0; }}\n#{uid} button, #{uid} .cq-nav a {{\n  border:0; text-decoration:none; padding:10px 14px; border-radius:10px;\n  font-weight:bold; cursor:pointer; display:inline-block; margin:6px 6px 0 0;\n  background:{t['panel2']}; color:{t['text']};\n}}\n#{uid} .cq-next, #{uid} .cq-nav .primary {{ background:{t['primary']}; color:{t['primary_text']}; }}\n#{uid} .cq-controls, #{uid} .cq-nav {{ margin-top:22px; }}\n#{uid} .cq-warn {{\n  background:#422006; color:#fde68a; border-left:4px solid #facc15;\n  border-radius:10px; padding:12px; margin-bottom:18px;\n}}\n"
    @staticmethod
    def js(uid, page_id):
        safe_id = json.dumps(page_id)
        return f'\n(function() {{\n  const root = document.getElementById("{uid}");\n  const pageId = {safe_id};\n  const steps = Array.from(root.querySelectorAll(".cq-step"));\n  const total = steps.length || 1;\n  const key = "cq-progress-" + pageId;\n  let current = parseInt(localStorage.getItem(key) || "0", 10);\n\n  const $ = s => root.querySelector(s);\n  const $$ = s => Array.from(root.querySelectorAll(s));\n  const clamp = v => Math.min(Math.max(v, 0), total - 1);\n\n  function render() {{\n    current = clamp(current);\n    steps.forEach((s, i) => s.style.display = i <= current ? "block" : "none");\n    $(".cq-progress-fill").style.width = (((current + 1) / total) * 100) + "%";\n    $(".cq-counter").textContent = "Bloco " + (current + 1) + " de " + total;\n    $(".cq-prev").disabled = current === 0;\n    $(".cq-next").disabled = current >= total - 1;\n    localStorage.setItem(key, current);\n  }}\n\n  $(".cq-prev").onclick = () => {{ current--; render(); }};\n  $(".cq-next").onclick = () => {{ current++; render(); }};\n  $(".cq-show").onclick = () => {{ current = total - 1; render(); }};\n  $(".cq-reset").onclick = () => {{ current = 0; render(); }};\n\n  $$(".cq-check").forEach(c => {{\n    const k = "cq-check-" + c.dataset.key;\n    c.checked = localStorage.getItem(k) === "true";\n    c.onchange = () => localStorage.setItem(k, c.checked ? "true" : "false");\n  }});\n\n  $$(".cq-answer").forEach(a => {{\n    const k = "cq-answer-" + a.dataset.key;\n    a.value = localStorage.getItem(k) || "";\n    a.oninput = () => localStorage.setItem(k, a.value);\n  }});\n\n  $$(".cq-copy").forEach(btn => {{\n    btn.onclick = () => {{\n      const text = btn.parentElement.querySelector(".cq-answer")?.value || "";\n      navigator.clipboard?.writeText(text);\n      btn.textContent = "Copiado!";\n      setTimeout(() => btn.textContent = "Copiar resposta", 1200);\n    }};\n  }});\n\n  $$(".cq-quiz-option").forEach(btn => {{\n    btn.onclick = () => {{\n      const ok = btn.dataset.value === btn.dataset.correct;\n      const fb = btn.parentElement.parentElement.querySelector(".cq-quiz-feedback");\n      fb.textContent = ok ? "Correto." : "Revise e tente novamente.";\n      fb.style.color = ok ? "#86efac" : "#fca5a5";\n    }};\n  }});\n\n  const reportBtn = $(".cq-report");\n  if (reportBtn) reportBtn.onclick = () => {{\n    const checks = $$(".cq-check-row").map(row => {{\n      const c = row.querySelector("input");\n      const txt = row.querySelector("span").textContent;\n      return (c.checked ? "✅ " : "⬜ ") + txt;\n    }}).join("\\n");\n    const answers = $$(".cq-answer").map((a, i) => {{\n      return "Resposta " + (i + 1) + ":\\n" + a.value;\n    }}).join("\\n\\n");\n    navigator.clipboard?.writeText("# Relatório - " + pageId + "\\n\\n" + checks + "\\n\\n" + answers);\n    reportBtn.textContent = "Relatório copiado!";\n    setTimeout(() => reportBtn.textContent = "Relatório final", 1400);\n  }};\n\n  const exportBtn = $(".cq-export");\n  if (exportBtn) exportBtn.onclick = () => {{\n    const html = root.outerHTML;\n    const blob = new Blob([html], {{type:"text/html"}});\n    const url = URL.createObjectURL(blob);\n    const a = document.createElement("a");\n    a.href = url;\n    a.download = pageId + ".html";\n    a.click();\n    URL.revokeObjectURL(url);\n  }};\n\n  render();\n}})();\n'
@CQRenderer.handler('checklist')
def _(doc, block, index, theme):
    html = ''.join((f"<label class='cq-check-row'><input class='cq-check' data-key='{escape(doc.id)}-{i}' type='checkbox'> <span>{escape(item)}</span></label>" for i, item in enumerate(block.items)))
    return CQRenderer.shell(doc, block, index, html)
@CQRenderer.handler('quiz')
def _(doc, block, index, theme):
    lines = CQUtil.lines(block.content)
    question = lines[0] if lines else 'Questão'
    correct = ''
    options = []
    for line in lines[1:]:
        if line.lower().startswith('correta:'):
            correct = line.split(':', 1)[1].strip().upper()
        else:
            options.append(line)
    letters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    opts = ''.join((f"<button class='cq-quiz-option' data-correct='{escape(correct)}' data-value='{letters[i]}'>{escape(opt)}</button>" for i, opt in enumerate(options)))
    return CQRenderer.shell(doc, block, index, f"<p><b>{escape(question)}</b></p>{opts}<div class='cq-quiz-feedback'></div>")
@CQRenderer.handler('resposta')
def _(doc, block, index, theme):
    key = escape(f'{doc.id}-answer-{index}')
    html = f"<p>{escape(block.content)}</p><textarea class='cq-answer' data-key='{key}'></textarea><button class='cq-copy'>Copiar resposta</button>"
    return CQRenderer.shell(doc, block, index, html)
@CQRenderer.handler('codigo')
def _(doc, block, index, theme):
    return CQRenderer.shell(doc, block, index, CQRenderer.code_html(block.content))
@CQRenderer.handler('execucao')
def _(doc, block, index, theme):
    return CQRenderer.shell(doc, block, index, CQRenderer.execucao_html(block.content, title='Execução', interactive=False))
@CQRenderer.handler('interativo')
def _(doc, block, index, theme):
    return CQRenderer.shell(doc, block, index, CQRenderer.execucao_html(block.content, title='Interativo', interactive=True))
@CQRenderer.handler('formula')
def _(doc, block, index, theme):
    return CQRenderer.shell(doc, block, index, f'<div>\\[{escape(block.content)}\\]</div>')
@CQRenderer.handler('comparacao')
def _(doc, block, index, theme):
    parts = block.content.split('---')
    left = escape(parts[0].strip()) if parts else ''
    right = escape(parts[1].strip()) if len(parts) > 1 else ''
    html = f"<div style='display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;'><div style='background:#111827;border:1px solid #334155;border-radius:12px;padding:14px;color:#e2e8f0;'><b style='display:block;margin-bottom:8px;color:#f8fafc;'>Clássico</b><p style='margin:0;line-height:1.65;'>{left}</p></div><div style='background:#111827;border:1px solid #334155;border-radius:12px;padding:14px;color:#e2e8f0;'><b style='display:block;margin-bottom:8px;color:#f8fafc;'>Quântico</b><p style='margin:0;line-height:1.65;'>{right}</p></div></div>"
    return CQRenderer.shell(doc, block, index, html)
@CQRenderer.handler('capa')
def _(doc, block, index, theme):
    fields = CQUtil.cover_fields(block.content)
    meta = []
    for label, key in [('Aluno', 'author'), ('Disciplina', 'course'), ('Professor', 'teacher'), ('Instituição', 'institution'), ('Unidade', 'school')]:
        value = fields.get(key, '')
        if value:
            meta.append((label, value))
    for item in fields.get('meta', []):
        if ':' in item:
            label, value = [part.strip() for part in item.split(':', 1)]
        else:
            label, value = 'Meta', item
        meta.append((label, value))
    nav = []
    for item in fields.get('nav', []):
        if '|' in item:
            label, href = [part.strip() for part in item.split('|', 1)]
        elif '->' in item:
            label, href = [part.strip() for part in item.split('->', 1)]
        else:
            label, href = item, '#navegacao-rapida'
        nav.append((label, href))
    cover = CQRenderer.cover_html(fields.get('title') or doc.title, subtitle=fields.get('subtitle') or doc.subtitle, logo=fields.get('logo', ''), objective=fields.get('objective', ''), meta=meta, nav=nav, roadmap=fields.get('roadmap', []), theme=theme)
    return f"<div style='margin-bottom:14px'>{cover}</div>"
@CQRenderer.handler('layout')
def _(doc, block, index, theme):
    return CQRenderer.shell(doc, block, index, CQRenderer.layout_html(block.content))
class CQ:
    @staticmethod
    def _pairs(value):
        if not value:
            return []
        if isinstance(value, dict):
            return list(value.items())
        return list(value)
    @staticmethod
    def grid_html(*items, widths=None, gap='14px', align='start'):
        if len(items) == 1 and isinstance(items[0], (list, tuple)):
            items = tuple(items[0])
        track = ' '.join(widths) if widths else f"repeat({len(items)}, minmax(0, 1fr))"
        gap = CQStyle.val(gap, CQStyle.SPACE)
        cells = ''.join(f"<div style='min-width:0'>{item}</div>" for item in items)
        return f"<div style='display:grid;grid-template-columns:{track};gap:{gap};align-items:{align};'>{cells}</div>"
    @staticmethod
    def grid(*items, widths=None, gap='14px', align='start'):
        display(HTML(CQ.grid_html(*items, widths=widths, gap=gap, align=align)))
    @staticmethod
    def flex_html(*items, direction='row', gap='14px', justify='start', align='stretch', wrap=True):
        if len(items) == 1 and isinstance(items[0], (list, tuple)):
            items = tuple(items[0])
        gap = CQStyle.val(gap, CQStyle.SPACE)
        wrap_value = 'wrap' if wrap else 'nowrap'
        cells = ''.join(f"<div style='min-width:0'>{item}</div>" for item in items)
        return f"<div style='display:flex;flex-direction:{direction};gap:{gap};justify-content:{justify};align-items:{align};flex-wrap:{wrap_value};'>{cells}</div>"
    @staticmethod
    def flex(*items, direction='row', gap='14px', justify='start', align='stretch', wrap=True):
        display(HTML(CQ.flex_html(*items, direction=direction, gap=gap, justify=justify, align=align, wrap=wrap)))
    @staticmethod
    def card_html(title, body, accent='#cfd6e7', theme='dark'):
        t = CQRegistry.theme(theme)
        return f"<div style='background:{t['panel']};border-left:4px solid {accent};border-radius:12px;padding:16px;color:{t['soft']};line-height:1.7;'><div style='font-size:12px;font-weight:700;letter-spacing:1px;text-transform:uppercase;margin-bottom:10px;color:{accent};'>{escape(str(title))}</div><div>{body}</div></div>"
    @staticmethod
    def card(title, body, accent='#cfd6e7', theme='dark'):
        display(HTML(CQ.card_html(title, body, accent=accent, theme=theme)))
    @staticmethod
    def capa_html(titulo, subtitulo='', logo='', objetivo='', meta=None, navegacao=None, roteiro=None, anchor='navegacao-rapida', theme='dark'):
        return CQRenderer.cover_html(titulo, subtitle=subtitulo, logo=logo, objective=objetivo, meta=CQ._pairs(meta), nav=CQ._pairs(navegacao), roadmap=roteiro or [], anchor=anchor, theme=theme)
    @staticmethod
    def capa(titulo, subtitulo='', logo='', objetivo='', meta=None, navegacao=None, roteiro=None, anchor='navegacao-rapida', theme='dark'):
        display(HTML(CQ.capa_html(titulo, subtitulo=subtitulo, logo=logo, objetivo=objetivo, meta=meta, navegacao=navegacao, roteiro=roteiro, anchor=anchor, theme=theme)))
    @staticmethod
    def codigo_html(code, language='python'):
        return CQRenderer.code_html(code, language=language)
    @staticmethod
    def codigo(code, language='python'):
        display(HTML(CQ.codigo_html(code, language=language)))
    @staticmethod
    def execucao_html(code, title='Execução', language='python', interactive=False, namespace=None):
        return CQRenderer.execucao_html(code, title=title, language=language, interactive=interactive, namespace=namespace)
    @staticmethod
    def execucao(code, title='Execução', language='python', interactive=False, namespace=None):
        note = "Interativo em Python" if interactive else "Saída da execução"
        try:
            from ipywidgets import Output
        except Exception:
            display(HTML(CQ.execucao_html(code, title=title, language=language, interactive=interactive, namespace=namespace)))
            return

        display(HTML(f"""
<div style="border:1px solid #334155;border-radius:12px;overflow:hidden;background:#0f172a;color:#f8fafc;">
  <div style="display:flex;align-items:center;justify-content:space-between;padding:10px 14px;background:#111827;border-bottom:1px solid #334155;">
    <span style="font-size:12px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:#cfd6e7;">{escape(title)}</span>
    <span style="font-size:12px;color:#cfd6e7;">{escape(note)}</span>
  </div>
  <div style="border-bottom:1px solid #334155;">{CQRenderer.code_html(code, language=language)}</div>
</div>
"""))
        output = Output(layout={"border": "1px solid #334155", "padding": "12px", "margin": "0 0 14px 0"})
        display(output)
        with output:
            try:
                _run_python_live(code, namespace=namespace)
            except Exception:
                traceback.print_exc()
    @staticmethod
    def interativo_html(code, title='Interativo', language='python', namespace=None):
        return CQ.execucao_html(code, title=title, language=language, interactive=True, namespace=namespace)
    @staticmethod
    def interativo(code, title='Interativo', language='python', namespace=None):
        CQ.execucao(code, title=title, language=language, interactive=True, namespace=namespace)
    @staticmethod
    def aula(source: str):
        doc = CQParser.parse(source)
        display(HTML(CQRenderer.render(doc)))
    @staticmethod
    def exportar(source: str, filename='cq_export.html'):
        doc = CQParser.parse(source)
        html = CQRenderer.render(doc, standalone=True)
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(html)
        return filename
    @staticmethod
    def analisar(source: str):
        doc = CQParser.parse(source)
        items = ''.join((f'<li><b>@{escape(b.kind)}</b>: {escape((b.content or str(b.items))[:100])}</li>' for b in doc.blocks))
        warnings = ''.join((f'<li>{escape(w)}</li>' for w in doc.warnings + doc.errors)) or '<li>Nenhum aviso.</li>'
        display(HTML(f'\n        <div style="background:#0f172a;color:#f8fafc;border-radius:18px;padding:24px;font-family:Arial">\n          <h2>Diagnóstico CQ</h2>\n          <p><b>ID:</b> {escape(doc.id)} | <b>Título:</b> {escape(doc.title)} | <b>Blocos:</b> {len(doc.blocks)}</p>\n          <h3>Avisos</h3><ul>{warnings}</ul>\n          <h3>Estrutura</h3><ol>{items}</ol>\n        </div>\n        '))
    @staticmethod
    def ajuda():
        display(HTML('\n        <div style="background:#0f172a;color:#f8fafc;border-radius:18px;padding:24px;font-family:Arial">\n          <h2>Ajuda rápida CQ</h2>\n          <pre style="background:#1e293b;padding:14px;border-radius:10px;overflow:auto">\nCQ.aula("""\n@pagina\norientacoes\n\n@titulo\nOrientações\n\n@tema\nquantum\n\n@objetivo\nTexto do objetivo.\n\n@passo\nPrimeiro passo.\n\n@codigo\nprint(\"oi\")\n\n@execucao\nprint(\"resultado\")\n\n@quiz\nPergunta?\nA) Opção A\nB) Opção B\ncorreta: B\n\n@resposta\nExplique com suas palavras.\n\n@checklist\n- Item 1\n- Item 2\n""")\n\nCQ.capa(...)\nCQ.grid(...)\nCQ.execucao(...)\nCQ.interativo(...)\n          </pre>\n        </div>\n        '))
    @staticmethod
    def indice(pages):
        links = ''.join((f"<a href='#{escape(anchor)}' style='display:block;color:#f8fafc;text-decoration:none;padding:9px 0;border-bottom:1px solid #334155'>{escape(title)}</a>" for title, anchor in pages))
        display(HTML(f'\n        <a id="navegacao-rapida"></a>\n        <div style="background:#0f172a;color:#f8fafc;border-radius:18px;padding:24px;font-family:Arial">\n          <h2 style="margin-top:0">Navegação rápida</h2>\n          {links}\n        </div>\n        '))
    @staticmethod
    def limpar_estado(prefixo='cq'):
        display(HTML(f"""\n        <button onclick="\n          Object.keys(localStorage)\n            .filter(k => k.startsWith('{escape(prefixo)}'))\n            .forEach(k => localStorage.removeItem(k));\n          this.innerText='Estado limpo';\n        " style="background:#dc2626;color:white;border:0;padding:10px 14px;border-radius:10px;font-weight:bold;cursor:pointer">\n          Limpar estado salvo\n        </button>\n        """))
