"""GUI del pipeline CMF.

La ventana viva es `unified_window` (la lanza `run_pipeline_gui.py`). Este `__init__` no
importa nada a proposito: en servidores headless no hay tkinter, y `.pipeline` --que usa
`run_pipeline_cli.py`-- tiene que seguir siendo importable sin arrastrar la interfaz.

Antes esto importaba la GUI legacy (`main_window`) dentro de un try/except, asi que en
headless fallaba en silencio y dejaba `CMFScraperGUI = None`.
"""

__version__ = "1.0.0"
