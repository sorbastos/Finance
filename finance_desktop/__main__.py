"""Entrada Qt do aplicativo; execute com o Python da .venv do projeto.

--database permite desenvolvimento isolado. --smoke-test encerra a janela
automaticamente e nunca deve ser executado contra o banco pessoal.
"""
import argparse
import os
import sys
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication
from shiboken6 import delete

from .controller import Controller
from .service import FinanceService


def main() -> int:
    """Mantém serviços vivos até o encerramento da engine e fecha o SQLite."""
    parser = argparse.ArgumentParser(description='Finance • despesas locais')
    parser.add_argument('--database', type=Path, help='Banco alternativo para testes')
    parser.add_argument('--smoke-test', action='store_true', help='Abre e encerra após renderizar')
    parser.add_argument('--screenshot', type=Path, help='Salva uma captura da janela de teste')
    args = parser.parse_args()
    if (args.smoke_test or args.screenshot) and args.database is None:
        parser.error('Testes e capturas exigem --database com um banco de teste.')
    if sys.prefix == sys.base_prefix:
        parser.error('Use bash instalar.sh e bash iniciar.sh: o aplicativo exige ambiente virtual.')
    database = args.database or Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'minhas-despesas/despesas.sqlite3'
    app = QApplication(sys.argv[:1])
    app.setApplicationName('Finance')
    app.setOrganizationName('FinanceLocal')
    QQuickStyle.setStyle('Basic')
    service = FinanceService(database)
    controller = Controller(service)
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty('finance', controller)
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parent / 'qml/Main.qml')))
    if not engine.rootObjects():
        service.close()
        return 1

    def capture_and_exit() -> None:
        """Captura somente quando pedida e após o primeiro layout da cena."""
        if args.screenshot:
            engine.rootObjects()[0].grabWindow().save(str(args.screenshot))
        if args.smoke_test:
            app.quit()

    if args.smoke_test or args.screenshot:
        QTimer.singleShot(1200, capture_and_exit)
    result = app.exec()
    # Destrói os objetos QML antes dos serviços usados em seus bindings.
    delete(engine)
    service.close()
    return result


if __name__ == '__main__':
    raise SystemExit(main())
