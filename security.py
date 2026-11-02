"""Proteções locais de arquivos financeiros, independentes da interface Qt."""
import os
from pathlib import Path

MAX_IMPORT_BYTES = 20_000_000


def read_import_file(path: Path) -> bytes:
    """Lê no máximo 20 MB mais um byte, sem confiar somente no tamanho informado."""
    if path.suffix.lower() not in ('.ofx', '.csv', '.xlsx'):
        raise ValueError('Selecione um arquivo OFX, CSV ou XLSX.')
    with path.open('rb') as source:
        if os.fstat(source.fileno()).st_size > MAX_IMPORT_BYTES:
            raise ValueError('Arquivo muito grande. O limite de importação é 20 MB.')
        raw = source.read(MAX_IMPORT_BYTES + 1)
    if len(raw) > MAX_IMPORT_BYTES:
        raise ValueError('Arquivo muito grande. O limite de importação é 20 MB.')
    return raw


def prepare_private_database(path: Path) -> None:
    """Cria/restringe o arquivo financeiro a seu proprietário em sistemas POSIX.

    Nunca trunca conteúdo nem segue links simbólicos no arquivo de destino.
    Somente o diretório dedicado do aplicativo tem permissões existentes alteradas;
    diretórios escolhidos pelo usuário, como Documentos, não são modificados.
    """
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name == 'posix' and path.parent.name == 'minhas-despesas':
        if path.parent.is_symlink():
            raise ValueError('O diretório de dados não pode ser um link simbólico.')
        path.parent.chmod(0o700)
    flags = os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        if os.name == 'posix':
            os.fchmod(descriptor, 0o600)
    finally:
        os.close(descriptor)
