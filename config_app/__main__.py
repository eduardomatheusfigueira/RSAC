#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Entry point para execução como módulo: python -m config_app

Permite executar a aplicação de qualquer diretório:
    cd /qualquer/lugar
    python -m config_app
"""

from config_app.utils.platform_compat import configure_dpi_awareness

# Configurar DPI awareness ANTES de importar tkinter
configure_dpi_awareness()

from config_app.main import SystematicReviewApp


def main():
    app = SystematicReviewApp()
    app.mainloop()


if __name__ == "__main__":
    main()
