"""Lectura del corpus y segmentación en fragmentos con metadatos de origen.

La cita de fuente es el requisito central del sistema, y una cita solo es
verificable si el fragmento sabe de dónde salió. Por eso la segmentación no
devuelve texto suelto: devuelve texto más documento, sección y posición.
"""

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
        """Texto con su procedencia incorporada, tal como se indexa.

        Al partir un documento, cada fragmento pierde el contexto de dónde
        venía. El caso que lo reveló: la sección "Plazo de entrega" de la
        historia clínica dice "la copia debe entregarse dentro de las 48
        horas" y no menciona en ningún lado de qué copia habla. Para el
        buscador era una frase suelta sobre plazos, y ante la pregunta
        "¿en cuánto tiempo me entregan la historia clínica?" perdía contra
        secciones que repetían "historia clínica" sin tener el dato.

        Anteponer el encabezado le devuelve al fragmento el tema del que
        habla, tanto para la búsqueda por significado como para la búsqueda
        por término exacto. Y como usa el mismo formato que se le pide al
        modelo para citar, la cita queda a la vista del propio modelo.
        """
        return f"[{self.documento} · {self.seccion}]\n\n{self.texto}"


# Encabezados markdown (#, ##, ...) y títulos en MAYÚSCULAS sobre línea propia.
_ENCABEZADO = re.compile(r"^\s{0,3}(#{1,6})\s+(.*\S)\s*$|^([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ0-9 ,.\-/()]{6,})\s*$")


def _identificador(documento: str, orden: int, texto: str) -> str:
    """Id estable: mismo contenido en la misma posición produce el mismo id.

    Permite reindexar sin duplicar. Azure AI Search solo admite letras,
    números, guiones, guiones bajos y signos igual en la clave.
    """
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
    """Segmenta respetando límites de párrafo cuando es posible.

    Cortar a la mitad de una frase produce fragmentos que el modelo cita mal,
    porque le falta el sujeto o la condición. Se acumulan párrafos hasta
    alcanzar el tamaño objetivo, y solo se parte un párrafo si por sí solo
    ya excede ese tamaño.
    """
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

    # README.md queda fuera a propósito: documenta el origen del corpus, no
    # forma parte de él. Indexarlo haría que el sistema pudiera citar sus
    # propias notas internas como si fueran documentación institucional.
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
