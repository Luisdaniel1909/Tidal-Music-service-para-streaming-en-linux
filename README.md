# Tidal Music service

![GitHub](https://img.shields.io/github/license/FUMR/tidal-async?style=flat-square)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000?style=flat-square)](https://github.com/psf/black)
[![Conventional Commits](https://img.shields.io/badge/Conventional%20Commits-1.0.0-yellow?style=flat-square)](https://conventionalcommits.org)

## Desarrollo
### Instalación de dependencias
```sh
# Instalación de todo
poetry install

# Instalación linters (no se aprobarán PR sin linter)
poetry run pre-commit install

# Instalar linters de commit-msg (Los PR con nombres de confirmación incorrectos serán eliminados)
poetry run pre-commit install --hook-type commit-msg
```
