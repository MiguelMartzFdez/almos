from setuptools import setup, find_packages
version = "1.0.0"
setup(
    name="almos_kit",
    packages=find_packages(include=["almos*", "edbo*"], exclude=["tests", "tests*"]),
    package_data={"almos": ["icons/*"]},
    version=version,
    license="MIT",
    description="Active Learning Molecular Selection",
    long_description="Documentation in Read The Docs: https://almos.readthedocs.io",
    long_description_content_type="text/markdown",
    author="Miguel Martínez Fernández, Susana García Abellán, David Dalmau Ginesta, Juan V. Alegre Requena",
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
        "Development Status :: 5 - Production/Stable",  # Chose either "3 - Alpha", "4 - Beta" or "5 - Production/Stable" as the current state of your package
        "Intended Audience :: Developers",  # Define that your audience are developers
        "Topic :: Software Development :: Build Tools",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    
    install_requires=[
        # --- Core ---
        "aqme==1.7.3",
        "robert==2.0.2",

        "numpy>=1.26,<2.0",  
        "pandas>=2.2,<2.3",
        "scikit-learn>=1.6,<1.7",
        "scipy>=1.14,<1.16",

        "matplotlib>=3.8,<3.11",
        "plotly>=5.20,<6.0",

        "pca==2.0.9",
        "kneed==0.8.5",
        "pdfplumber==0.11.5",
        "rdkit==2024.3.3",

        # --- BO ---
        "botorch==0.7.2",
        "gpytorch==1.9.0",
        "torch>=2.1,<3.0",

        # --- legacy ---
        "idaes-pse==1.5.1",

        # --- utils ---
        "sympy>=1.12,<1.14",
        "lxml>=4.6,<5.0",
        "Jinja2>=3.0,<3.2",
        "ordered-set==4.0.2",
        "pareto==1.1.1.post3",
        "pymoo==0.5.0",
        "seaborn>=0.13,<0.14",
        "joypy==0.2.6",
        "tqdm",

        # Fix pkg_resources
        "setuptools<81",
    ],
    python_requires=">=3.10",
    include_package_data=True,
)