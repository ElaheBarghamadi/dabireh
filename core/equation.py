"""LaTeX-subset parser for equations (Qt-free).

The parser produces a small tree of :class:`Node` objects.  The tree is laid
out with explicit left-to-right coordinates by ``editor/equation_render.py``
and converted to Office Math (OMML) by :func:`to_omml`; the LaTeX source is
what the document stores, and it is never reordered for display.

Supported: fractions, powers, subscripts, roots, sums/products/integrals with
limits, ``\\lim``, matrices (matrix/pmatrix/bmatrix/vmatrix), ``\\vec``/``\\hat``/
``\\bar``, ``\\left``/``\\right`` delimiters, Greek letters, common operators and
relations, ``\\text``/``\\mathrm``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from xml.sax.saxutils import escape

GREEK = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ϵ", "varepsilon": "ε", "zeta": "ζ",
    "eta": "η", "theta": "θ", "vartheta": "ϑ", "iota": "ι", "kappa": "κ", "lambda": "λ", "mu": "μ", "nu": "ν",
    "xi": "ξ", "pi": "π", "rho": "ρ", "sigma": "σ", "tau": "τ", "upsilon": "υ", "phi": "ϕ", "varphi": "φ",
    "chi": "χ", "psi": "ψ", "omega": "ω", "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ",
    "Pi": "Π", "Sigma": "Σ", "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω",
}
SYMBOLS = {
    "times": "×", "cdot": "·", "div": "÷", "pm": "±", "mp": "∓", "leq": "≤", "le": "≤", "geq": "≥", "ge": "≥",
    "neq": "≠", "ne": "≠", "approx": "≈", "equiv": "≡", "sim": "∼", "propto": "∝", "infty": "∞",
    "partial": "∂", "nabla": "∇", "to": "→", "rightarrow": "→", "leftarrow": "←", "Rightarrow": "⇒",
    "Leftarrow": "⇐", "leftrightarrow": "↔", "Leftrightarrow": "⇔", "in": "∈", "notin": "∉", "subset": "⊂",
    "subseteq": "⊆", "supset": "⊃", "cup": "∪", "cap": "∩", "emptyset": "∅", "forall": "∀", "exists": "∃",
    "neg": "¬", "land": "∧", "lor": "∨", "angle": "∠", "perp": "⊥", "parallel": "∥", "circ": "∘",
    "ldots": "…", "cdots": "⋯", "dots": "…", "prime": "′", "degree": "°", "ast": "∗", "star": "⋆",
    "langle": "⟨", "rangle": "⟩", "lbrace": "{", "rbrace": "}", "{": "{", "}": "}", "|": "‖", "%": "%",
    "mathbb{R}": "ℝ", "ell": "ℓ", "hbar": "ℏ", "oplus": "⊕", "otimes": "⊗",
}
BIG_OPERATORS = {"sum": "∑", "prod": "∏", "int": "∫", "iint": "∬", "oint": "∮", "bigcup": "⋃", "bigcap": "⋂"}
LIMIT_FUNCTIONS = {"lim", "max", "min", "sup", "inf"}
FUNCTIONS = {"sin", "cos", "tan", "cot", "sec", "csc", "arcsin", "arccos", "arctan", "sinh", "cosh", "tanh",
             "log", "ln", "exp", "det", "gcd", "deg", "dim", "ker", "mod"} | LIMIT_FUNCTIONS
ACCENTS = {"vec", "hat", "bar", "overline", "tilde", "dot"}
SPACES = {",": 0.17, ";": 0.28, ":": 0.22, "!": -0.1, "quad": 1.0, "qquad": 2.0, " ": 0.3}
MATRIX_DELIMITERS = {"matrix": ("", ""), "pmatrix": ("(", ")"), "bmatrix": ("[", "]"),
                     "vmatrix": ("|", "|"), "Bmatrix": ("{", "}"), "cases": ("{", "")}
BLACKBOARD = {"R": "ℝ", "N": "ℕ", "Z": "ℤ", "Q": "ℚ", "C": "ℂ"}
RELATIONS = set("=<>≤≥≠≈≡∼∝→←⇒⇐↔⇔∈∉⊂⊆⊃")
BINARY = set("+−×·÷±∓∪∩∧∨⊕⊗∘")


class EquationError(ValueError):
    """The LaTeX source could not be parsed."""


@dataclass
class Node:
    """kind: row | sym | text | frac | sqrt | script | bigop | matrix | accent | delim | space"""

    kind: str
    text: str = ""
    items: list[Node] = field(default_factory=list)
    sub: Node | None = None
    sup: Node | None = None
    rows: list[list[Node]] = field(default_factory=list)
    left: str = ""
    right: str = ""
    limits: bool = False  # scripts are placed above/below in display mode
    upright: bool = False
    size: float = 0.0


def _tokenize(source: str) -> list[str]:
    tokens: list[str] = []
    index = 0
    while index < len(source):
        char = source[index]
        if char == "\\":
            end = index + 1
            while end < len(source) and source[end].isalpha():
                end += 1
            if end == index + 1:
                end = min(len(source), index + 2)
            tokens.append(source[index:end])
            index = end
        elif char.isspace():
            index += 1
        else:
            tokens.append(char)
            index += 1
    return tokens


class _Parser:
    def __init__(self, source: str) -> None:
        self.tokens = _tokenize(source)
        self.position = 0

    def peek(self) -> str | None:
        return self.tokens[self.position] if self.position < len(self.tokens) else None

    def take(self) -> str:
        token = self.peek()
        if token is None:
            raise EquationError("عبارت ناتمام است.")
        self.position += 1
        return token

    def expect(self, token: str) -> None:
        if self.take() != token:
            raise EquationError(f"«{token}» انتظار می‌رفت.")

    def parse_row(self, stops: tuple[str, ...] = ()) -> Node:
        items: list[Node] = []
        while (token := self.peek()) is not None and token not in stops:
            if token == "}":
                raise EquationError("آکولاد بسته بدون آکولاد باز آمده است.")
            atom = self.parse_atom()
            atom = self.parse_scripts(atom)
            items.append(atom)
        return Node("row", items=items)

    def parse_scripts(self, base: Node) -> Node:
        sub = sup = None
        while self.peek() in ("^", "_", "'"):
            token = self.take()
            if token == "'":
                prime = Node("sym", "′")
                sup = Node("row", items=[*(sup.items if sup and sup.kind == "row" else [sup] if sup else []), prime])
            elif token == "^":
                sup = self.parse_group()
            else:
                sub = self.parse_group()
        if sub is None and sup is None:
            return base
        if base.kind == "bigop":
            base.sub, base.sup = sub, sup
            return base
        return Node("script", items=[base], sub=sub, sup=sup)

    def parse_group(self) -> Node:
        """One argument: a braced group or a single atom."""
        if self.peek() == "{":
            self.take()
            row = self.parse_row(("}",))
            self.expect("}")
            return row
        return self.parse_atom()

    def raw_group(self) -> str:
        self.expect("{")
        parts: list[str] = []
        depth = 1
        while True:
            token = self.take()
            if token == "{":
                depth += 1
            elif token == "}":
                depth -= 1
                if depth == 0:
                    return "".join(parts)
            parts.append(token)

    def delimiter(self) -> str:
        token = self.take()
        if token == ".":
            return ""
        if token.startswith("\\"):
            return SYMBOLS.get(token[1:], token[1:])
        return token

    def parse_atom(self) -> Node:
        token = self.take()
        if token == "{":
            row = self.parse_row(("}",))
            self.expect("}")
            return row
        if token in ("^", "_"):
            raise EquationError("توان یا زیرنویس بدون پایه آمده است.")
        if not token.startswith("\\"):
            if token == "-":
                token = "−"
            return Node("sym", token, upright=not token.isalpha())
        name = token[1:]
        if name in ("frac", "dfrac", "tfrac"):
            return Node("frac", items=[self.parse_group(), self.parse_group()])
        if name == "sqrt":
            index = None
            if self.peek() == "[":
                self.take()
                index = self.parse_row(("]",))
                self.expect("]")
            return Node("sqrt", items=[self.parse_group()], sup=index)
        if name in BIG_OPERATORS:
            return Node("bigop", BIG_OPERATORS[name], limits=name in ("sum", "prod", "bigcup", "bigcap"))
        if name in FUNCTIONS:
            if name in LIMIT_FUNCTIONS:
                return Node("bigop", name, limits=True, upright=True)
            return Node("sym", name, upright=True, left="func")
        if name in ACCENTS:
            return Node("accent", name, items=[self.parse_group()])
        if name in ("text", "mathrm", "textrm", "operatorname", "mathbf", "textbf"):
            return Node("text", self.raw_group() if name.startswith("text") else self._flat(self.parse_group()),
                        upright=True, left="bold" if name.endswith("bf") else "")
        if name == "mathbb":
            letter = self._flat(self.parse_group())
            return Node("sym", BLACKBOARD.get(letter, letter), upright=True)
        if name == "left":
            left = self.delimiter()
            body = self.parse_row(("\\right",))
            self.expect("\\right")
            return Node("delim", items=[body], left=left, right=self.delimiter())
        if name == "begin":
            environment = self.raw_group()
            if environment not in MATRIX_DELIMITERS:
                raise EquationError(f"محیط «{environment}» پشتیبانی نمی‌شود.")
            return self.parse_matrix(environment)
        if name in SPACES:
            return Node("space", size=SPACES[name])
        if name in GREEK:
            return Node("sym", GREEK[name], upright=name[0].isupper())
        if name in SYMBOLS:
            return Node("sym", SYMBOLS[name], upright=True)
        if name == "\\":
            return Node("space", size=1.0)
        raise EquationError(f"فرمان «\\{name}» شناخته نشد.")

    def parse_matrix(self, environment: str) -> Node:
        rows: list[list[Node]] = [[]]
        while True:
            cell = self.parse_row(("&", "\\\\", "\\end"))
            rows[-1].append(cell)
            token = self.take()
            if token == "\\\\":
                rows.append([])
            elif token == "\\end":
                if self.raw_group() != environment:
                    raise EquationError("پایان محیط با آغاز آن یکی نیست.")
                break
        if rows and len(rows[-1]) == 1 and not rows[-1][0].items and len(rows) > 1:
            rows.pop()
        left, right = MATRIX_DELIMITERS[environment]
        return Node("matrix", rows=rows, left=left, right=right)

    @staticmethod
    def _flat(node: Node) -> str:
        if node.kind in ("sym", "text"):
            return node.text
        return "".join(_Parser._flat(item) for item in node.items)


def parse(source: str) -> Node:
    """Parse LaTeX math into a tree; raises :class:`EquationError`."""
    parser = _Parser(source.strip().strip("$"))
    row = parser.parse_row()
    if parser.peek() is not None:
        raise EquationError("عبارت معتبر نیست.")
    return row


def is_valid(source: str) -> bool:
    try:
        parse(source)
    except EquationError:
        return False
    return True


# -------------------------------------------------------------------- OMML
_M = "http://schemas.openxmlformats.org/officeDocument/2006/math"


def _run(text: str, upright: bool = False) -> str:
    properties = '<m:rPr><m:sty m:val="p"/></m:rPr>' if upright else ""
    return f'<m:r>{properties}<m:t xml:space="preserve">{escape(text)}</m:t></m:r>'


def _arg(tag: str, node: Node | None) -> str:
    return f"<m:{tag}>{_omml(node) if node is not None else ''}</m:{tag}>"


def _omml(node: Node) -> str:
    kind = node.kind
    if kind == "row":
        return "".join(_omml(item) for item in node.items)
    if kind == "sym":
        return _run(node.text, node.upright)
    if kind == "text":
        return _run(node.text, True)
    if kind == "space":
        return _run(" ")
    if kind == "frac":
        return f"<m:f>{_arg('num', node.items[0])}{_arg('den', node.items[1])}</m:f>"
    if kind == "sqrt":
        if node.sup is None:
            return f'<m:rad><m:radPr><m:degHide m:val="1"/></m:radPr><m:deg/>{_arg("e", node.items[0])}</m:rad>'
        return f"<m:rad>{_arg('deg', node.sup)}{_arg('e', node.items[0])}</m:rad>"
    if kind == "script":
        base = _arg("e", node.items[0])
        if node.sub is not None and node.sup is not None:
            return f"<m:sSubSup>{base}{_arg('sub', node.sub)}{_arg('sup', node.sup)}</m:sSubSup>"
        if node.sub is not None:
            return f"<m:sSub>{base}{_arg('sub', node.sub)}</m:sSub>"
        return f"<m:sSup>{base}{_arg('sup', node.sup)}</m:sSup>"
    if kind == "bigop":
        if node.upright:  # lim, max, …
            name = _run(node.text, True)
            if node.sub is None:
                return name
            return f"<m:limLow><m:e>{name}</m:e>{_arg('lim', node.sub)}</m:limLow>"
        location = "undOvr" if node.limits else "subSup"
        hide = ('<m:subHide m:val="1"/>' if node.sub is None else "") + (
            '<m:supHide m:val="1"/>' if node.sup is None else "")
        return (f'<m:nary><m:naryPr><m:chr m:val="{node.text}"/><m:limLoc m:val="{location}"/>{hide}</m:naryPr>'
                f"{_arg('sub', node.sub)}{_arg('sup', node.sup)}<m:e/></m:nary>")
    if kind == "accent":
        if node.text in ("bar", "overline"):
            return f'<m:bar><m:barPr><m:pos m:val="top"/></m:barPr>{_arg("e", node.items[0])}</m:bar>'
        char = {"vec": "\u20d7", "hat": "\u0302", "tilde": "\u0303", "dot": "\u0307"}[node.text]
        return f'<m:acc><m:accPr><m:chr m:val="{char}"/></m:accPr>{_arg("e", node.items[0])}</m:acc>'
    if kind == "delim":
        return (f'<m:d><m:dPr><m:begChr m:val="{escape(node.left)}"/><m:endChr m:val="{escape(node.right)}"/></m:dPr>'
                f"{_arg('e', node.items[0])}</m:d>")
    if kind == "matrix":
        rows = "".join("<m:mr>" + "".join(_arg("e", cell) for cell in row) + "</m:mr>" for row in node.rows)
        matrix = f"<m:m>{rows}</m:m>"
        if not node.left and not node.right:
            return matrix
        return (f'<m:d><m:dPr><m:begChr m:val="{escape(node.left)}"/><m:endChr m:val="{escape(node.right)}"/></m:dPr>'
                f"<m:e>{matrix}</m:e></m:d>")
    return ""


def to_omml(source: str) -> str:
    """Office Math XML (``<m:oMath>``) for the LaTeX source."""
    return f'<m:oMath xmlns:m="{_M}">{_omml(parse(source))}</m:oMath>'


# ------------------------------------------------------ OMML -> LaTeX (import)
_REVERSE = {value: "\\" + key + " " for key, value in {**SYMBOLS, **GREEK}.items()
            if len(value) == 1 and key.isalpha() and value not in "{}%"}
_REVERSE["−"] = "-"
_REVERSE_BIG = {value: "\\" + key for key, value in BIG_OPERATORS.items()}


def _latex_text(text: str) -> str:
    return "".join(_REVERSE.get(char, char) for char in text)


def omml_to_latex(element) -> str:  # noqa: ANN001 - an lxml/ElementTree element
    """Best-effort LaTeX for an ``m:oMath`` element (used by DOCX import)."""

    def local(node) -> str:  # noqa: ANN001
        return node.tag.rsplit("}", 1)[-1]

    def child(node, name):  # noqa: ANN001, ANN202
        return next((item for item in node if local(item) == name), None)

    def inner(node) -> str:  # noqa: ANN001
        return "".join(convert(item) for item in node) if node is not None else ""

    def attribute(node, path: tuple[str, ...], default: str) -> str:  # noqa: ANN001
        for name in path:
            node = child(node, name) if node is not None else None
        if node is None:
            return default
        return next((value for key, value in node.attrib.items() if key.endswith("val")), default)

    def convert(node) -> str:  # noqa: ANN001
        name = local(node)
        if name == "r":
            text = "".join(item.text or "" for item in node if local(item) == "t")
            if text.isalpha() and len(text) > 1 and text.isascii():
                return ("\\" + text + " ") if text in FUNCTIONS else "\\text{" + text + "}"
            return _latex_text(text)
        if name == "f":
            return "\\frac{" + inner(child(node, "num")) + "}{" + inner(child(node, "den")) + "}"
        if name == "rad":
            degree = inner(child(node, "deg"))
            return "\\sqrt" + (f"[{degree}]" if degree else "") + "{" + inner(child(node, "e")) + "}"
        if name == "sSup":
            return "{" + inner(child(node, "e")) + "}^{" + inner(child(node, "sup")) + "}"
        if name == "sSub":
            return "{" + inner(child(node, "e")) + "}_{" + inner(child(node, "sub")) + "}"
        if name == "sSubSup":
            return ("{" + inner(child(node, "e")) + "}_{" + inner(child(node, "sub")) + "}^{"
                    + inner(child(node, "sup")) + "}")
        if name == "nary":
            operator = _REVERSE_BIG.get(attribute(node, ("naryPr", "chr"), "∫"), "\\int")
            sub, sup = inner(child(node, "sub")), inner(child(node, "sup"))
            return (operator + (f"_{{{sub}}}" if sub else "") + (f"^{{{sup}}}" if sup else "") + " "
                    + inner(child(node, "e")))
        if name == "limLow":
            return inner(child(node, "e")).strip() + "_{" + inner(child(node, "lim")) + "}"
        if name == "d":
            left = attribute(node, ("dPr", "begChr"), "(")
            right = attribute(node, ("dPr", "endChr"), ")")
            body = "".join(inner(item) for item in node if local(item) == "e")
            fix = {"{": "\\{", "}": "\\}", "": "."}
            return f"\\left{fix.get(left, left)}{body}\\right{fix.get(right, right)}"
        if name == "m":
            rows = [" & ".join(inner(cell) for cell in row if local(cell) == "e")
                    for row in node if local(row) == "mr"]
            return "\\begin{matrix}" + " \\\\ ".join(rows) + "\\end{matrix}"
        if name == "bar":
            return "\\bar{" + inner(child(node, "e")) + "}"
        if name == "acc":
            char = attribute(node, ("accPr", "chr"), "\u0302")
            command = {"\u20d7": "vec", "\u0302": "hat", "\u0303": "tilde", "\u0307": "dot"}.get(char, "hat")
            return f"\\{command}{{" + inner(child(node, "e")) + "}"
        if name.endswith("Pr"):
            return ""
        return inner(node)

    return inner(element).strip()
