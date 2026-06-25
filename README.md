<p align="center">
  <img src="almos/icons/almos_logo.png" alt="ALMOS logo" width="520">
</p>

<h2 align="center">ALMOS</h2>
<p align="center"><strong>Active Learning Molecular Selection</strong></p>

<p align="center">
  <a href="https://app.circleci.com/pipelines/github/MiguelMartzFdez/almos"><img src="https://img.shields.io/circleci/build/github/MiguelMartzFdez/almos?label=Circle%20CI&logo=circleci" alt="CircleCI"></a>
  <a href="https://codecov.io/gh/MiguelMartzFdez/almos"><img src="https://img.shields.io/codecov/c/github/MiguelMartzFdez/almos?label=Codecov&logo=codecov" alt="Codecov"></a>
  <a href="https://pepy.tech/project/almos-kit"><img src="https://pepy.tech/badge/almos-kit" alt="Downloads"></a>
  <a href="https://almos.readthedocs.io/"><img src="https://img.shields.io/readthedocs/almos?label=Read%20the%20Docs&logo=readthedocs" alt="Read the Docs"></a>
  <a href="https://pypi.org/project/almos-kit/"><img src="https://img.shields.io/pypi/v/almos-kit?cacheSeconds=300" alt="PyPI"></a>
</p>

---

# 🚀 Installation

Choose the installation method that best fits your workflow.

| Method | Recommended for |
|---------|-----------------|
| 🖥️ **EasyALMOS installers** | Users without Python experience |
| 📦 **Conda environment file** | Most Conda users |
| ⚙️ **Manual Conda + pip installation** | Advanced users |

---

# 🖥️ Option 1 — EasyALMOS Desktop Installers (Recommended)

The easiest way to use **ALMOS** is through the **EasyALMOS** desktop application.

✅ No Python installation required.

✅ No Conda configuration.

✅ No terminal commands.

<p align="center">
  <a href="https://github.com/MiguelMartzFdez/almos/releases/latest">
    <strong>⬇️ Download EasyALMOS</strong>
  </a>
</p>

| Operating System | Download | Installation |
|------------------|----------|--------------|
| 🪟 Windows | `easyalmos-<VERSION>.exe` | Double-click the installer, then launch **EasyALMOS** from the Start Menu. |
| 🍎 macOS | `easyalmos-<VERSION>.dmg` | Drag **EasyALMOS.app** into Applications. |
| 🐧 Ubuntu / Debian | `easyalmos-<VERSION>.deb` | Double-click the package or run `sudo apt install ./easyalmos-<VERSION>.deb`. |

> **Note**
>
> EasyALMOS installs its own private ALMOS environment, completely isolated from your system Python or Conda installations.
>
> The first installation may take a few minutes while the environment is prepared.

---

# 📦 Option 2 — Install with the Conda Environment File

This is the recommended installation method for users already working with Conda.

### 1. Download the environment file

```bash
curl -O https://raw.githubusercontent.com/MiguelMartzFdez/almos/miguel/install/almos.yaml
```

### 2. Create the environment

```bash
conda env create -f almos.yaml
```

### 3. Activate it

```bash
conda activate almos
```

That's it! 🎉

---

# ⚙️ Option 3 — Manual Conda + pip Installation

Use this option if you prefer creating the environment yourself.

### Create the environment

```bash
conda create -n almos python=3.11
```

### Activate it

```bash
conda activate almos
```

### Install ALMOS

```bash
pip install almos-kit
```

### Install ROBERT backend dependencies

```bash
conda install -y -c conda-forge glib gtk3 pango mscorefonts
```

### Install AQME dependencies

```bash
conda install -y -c conda-forge openbabel=3.1.1 xtb=6.7.1
```
---

# 🚀 Launch

Start the command-line interface:

```bash
almos
```

Launch the graphical interface:

```bash
easyalmos
```
---

# 📚 Documentation

Complete documentation is available at

👉 https://almos.readthedocs.io

---

# 👨‍💻 Developers

| Developer | Contact |
|-----------|---------|
| Miguel Martinez Fernandez | miguel.martinez@csic.es |
| Susana P. Garcia Abellan | sg.abellan@csic.es |
| David Dalmau Ginesta | ddalmau@unizar.es |
| Juan V. Alegre-Requena | jv.alegre@csic.es |

Suggestions and contributions are welcome through **GitHub Issues** and **Pull Requests**.

---

# 📄 License

ALMOS is distributed under the **MIT License**.
