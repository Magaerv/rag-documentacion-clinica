"""Lee el corpus y lo parte en fragmentos con documento, sección y posición."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class Fragmento:
    id: str
    texto: str
    documento: str      # nombre del archivo de origen
    seccion: str        # título de la sección a la que pertenece
    orden: int          # posición del fragmento dentro del documento

    def como_dict(self) -> dict:
        return asdict(self)

    def texto_indexado(self) -> str:
        """Texto con el encabezado [documento · sección], tal como se indexa.

        Sin el encabezado, fragmentos cortos pierden el tema (p. ej. "la copia
        debe entregarse dentro de las 48 horas") y no se recuperan bien.
        """
        return f"[{self.documento} · {self.seccion}]\n\n{self.texto}"


# Encabezados markdown (#, ##, ...) y títulos en MAYÚSCULAS sobre línea propia.
_ENCABEZADO = re.compile(r"^\s{0,3}(#{1,6})\s+(.*\S)\s*$|^([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ0-9 ,.\-/()]{6,})\s*$")


def _identificador(documento: str, orden: int, texto: str) -> str:
    """Id estable para poder reindexar sin duplicar."""
    firma = hashlib.sha1(f"{documento}:{orden}:{texto}".encode("utf-8")).hexdigest()
    return f"{firma[:24]}"


def _secciones(texto: str) -> list[tuple[str, str]]:
    """Parte el documento en (título de sección, cuerpo)."""
    secciones: list[tuple[str, str]] = []
    titulo_actual = "Sin sección"
    buffer: list[str] = []

    for linea in texto.splitlines():
        m = _ENCABEZADO.match(linea)
        if m:
            if buffer:
                secciones.append((titulo_actual, "\n".join(buffer).strip()))
                buffer = []
            titulo_actual = (m.group(2) or m.group(3) or "").strip()
        else:
            buffer.append(linea)

    if buffer:
        secciones.append((titulo_actual, "\n".join(buffer).strip()))

    return [(t, c) for t, c in secciones if c]


def _partir(texto: str, tamano: int, solapamiento: int) -> list[str]:
    """Agrupa párrafos hasta el tamaño objetivo; solo corta párrafos muy largos."""
    parrafos = [p.strip() for p in re.split(r"\n\s*\n", texto) if p.strip()]
    fragmentos: list[str] = []
    actual = ""

    for parrafo in parrafos:
        if len(parrafo) > tamano:
            if actual:
                fragmentos.append(actual)
                actual = ""
            for i in range(0, len(parrafo), tamano - solapamiento):
                fragmentos.append(parrafo[i : i + tamano])
            continue

        if len(actual) + len(parrafo) + 2 <= tamano:
            actual = f"{actual}\n\n{parrafo}".strip()
        else:
            if actual:
                fragmentos.append(actual)
            actual = parrafo

    if actual:
        fragmentos.append(actual)

    return fragmentos


def leer_corpus(directorio: Path, tamano: int, solapamiento: int) -> list[Fragmento]:
    """Devuelve todos los fragmentos del corpus, listos para indexar."""
    if not directorio.exists():
        raise FileNotFoundError(f"No existe el directorio de corpus: {directorio}")

    # README.md documenta el corpus, no se indexa.
    archivos = sorted(
        p
        for p in directorio.rglob("*")
        if p.suffix.lower() in {".md", ".txt"} and p.name.lower() != "readme.md"
    )
    if not archivos:
        raise RuntimeError(
            f"No hay archivos .md ni .txt en {directorio}. "
            "Ver corpus/README.md para el origen de los documentos."
        )

    resultado: list[Fragmento] = []

    for archivo in archivos:
        contenido = archivo.read_text(encoding="utf-8")
        orden = 0
        for titulo, cuerpo in _secciones(contenido):
            for trozo in _partir(cuerpo, tamano, solapamiento):
                resultado.append(
                    Fragmento(
                        id=_identificador(archivo.name, orden, trozo),
                        texto=trozo,
                        documento=archivo.name,
                        seccion=titulo,
                        orden=orden,
                    )
                )
                orden += 1

    return resultado


if __name__ == "__main__":
    import sys

    raiz = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(raiz / "src"))
    from config import Config

    cfg = Config.desde_entorno()
    fragmentos = leer_corpus(raiz / "corpus", cfg.tamano_fragmento, cfg.solapamiento)

    print(f"{len(fragmentos)} fragmentos desde {len({f.documento for f in fragmentos})} documento(s)\n")
    for f in fragmentos[:3]:
        print(f"[{f.documento} · {f.seccion}] {len(f.texto)} car.")
        print(f"  {f.texto[:120].replace(chr(10), ' ')}...\n")
