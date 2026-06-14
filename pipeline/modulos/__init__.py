# -*- coding: utf-8 -*-
"""
pipeline — Pacote de geração de vídeos com legendas morfológicas multilíngues.

Importações principais:
    from pipeline.config import PipelineConfig
    from pipeline.groq_client import GroqClient
    from pipeline.video_pipeline import VideoPipeline
    from pipeline.checkpoint import Checkpoint
    from pipeline.video_pipeline import ClassificacaoPendenteError
"""
from config import PipelineConfig
from groq_client import GroqClient
from video_pipeline import VideoPipeline, ClassificacaoPendenteError
from checkpoint import Checkpoint
from classification import Classifier
from drive_utils import DriveClient
from srt_utils import ler_srt, salvar_srt, eliminar_gaps
from ffmpeg_utils import gerar_ass, queimar_legendas_ass, obter_duracao
from models import Legenda, Palavra, Clipe

__all__ = [
    "PipelineConfig",
    "GroqClient",
    "VideoPipeline",
    "Checkpoint",
    "Classifier",
    "DriveClient",
    "ler_srt",
    "salvar_srt",
    "eliminar_gaps",
    "gerar_ass",
    "queimar_legendas_ass",
    "obter_duracao",
    "Legenda",
    "Palavra",
    "Clipe",
    "ClassificacaoPendenteError",  # ← adicionado
]