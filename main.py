from pathlib import Path

from app.core.downloader import Downloader
from app.core.format_selector import FormatSelector
from app.models import DownloadOptions, DownloadType


def main() -> None:
    url = input("Digite a URL: ").strip()

    downloader = Downloader()
    selector = FormatSelector()

    try:
        print("\nAnalisando mídia...")

        media = downloader.analyze(url)
        
        print("\nFormatos disponíveis:")

        for format_info in media.formats:
            print(
                f"ID: {format_info.format_id} | "
                f"Tipo: {format_info.media_type.value} | "
                f"Resolução: {format_info.width}x{format_info.height} | "
                f"Vídeo: {format_info.video_codec or '-'} | "
                f"Áudio: {format_info.audio_codec or '-'} | "
                f"Extensão: {format_info.extension or '-'}"
            )

        print(f"Título: {media.title}")
        print(f"Formatos encontrados: {len(media.formats)}")

        options = DownloadOptions(
            url=url,
            download_type=DownloadType.VIDEO,
            max_height=720,
            destination=Path("downloads"),
        )

        selection = selector.select(media, options)

        print("\nFormato selecionado:")

        if selection.video_format:
            print(
                f"Vídeo: {selection.video_format.format_id} "
                f"({selection.video_format.height}p)"
            )

        if selection.audio_format:
            print(
                f"Áudio: {selection.audio_format.format_id}"
            )

        if selection.requires_merge:
            print("A seleção requer FFmpeg.")

        print("\nIniciando download...")

        result = downloader.download(options, selection)

        if result.success:
            print(f"\nDownload concluído: {result.file_path}")
            print(f"Tamanho: {result.file_size} bytes")
        else:
            print(f"\nErro: {result.error_message}")

    except Exception as exc:
        print(f"\nErro: {exc}")


if __name__ == "__main__":
    main()