from setuptools import setup, find_packages
version = "0.1.2"
setup(
    name="almos_kit",
    packages=find_packages(exclude=["tests"]),
    package_data={"almos": ["icons/*"]},
    version=version,
    license="MIT",
    description="Active Learning Molecular Selection",
    long_description="Documentation in Read The Docs: https://almos.readthedocs.io",
    long_description_content_type="text/markdown",
    author="Miguel Martínez Fernández, Susana García Abellán, Juan V. Alegre Requena",
    author_email="miguel.martinez@csic.es, susanag.abellan@gmail.com",
    keywords=[
        "workflows",
        "machine learning",
        "cheminformatics",
        "clustering",
        "active learning",
        "automated",
    ],
    url="https://github.com/MiguelMartzFdez/almos",
    download_url=f"https://github.com/MiguelMartzFdez/almos/archive/refs/tags/{version}.tar.gz",
    classifiers=[
        "Development Status :: 3 - Alpha",  # Chose either "3 - Alpha", "4 - Beta" or "5 - Production/Stable" as the current state of your package
        "Intended Audience :: Developers",  # Define that your audience are developers
        "Topic :: Software Development :: Build Tools",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    
    install_requires=[
    "aqme==1.7.2",
    "robert==2.0.1",
    "plotly==5.24.1",
    "matplotlib==3.10.0",
    "numpy>=1.26.4,<3.0",
    "pandas>=2.2.2,<2.3",
    "pdfplumber==0.11.5",
    "rdkit==2024.3.3",
    "scikit_learn>=1.6,<1.7",
    "pca==2.0.9",
],

    python_requires=">=3.10",
    include_package_data=True,
    )