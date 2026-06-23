from setuptools import setup, find_packages
from almos.package_versions import ALMOS_VERSION, AQME_VERSION

version = ALMOS_VERSION
setup(
    name="almos_kit",
    packages=find_packages(include=["almos*"], exclude=["tests", "tests*"]),
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
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
    ],
    
    install_requires=[
        # --- Core ---
        f"aqme=={AQME_VERSION}",
        "robert==2.1.0",

        "pandas==2.3.3",
        "scipy>=1.14,<1.16",
        "hdbscan>=0.8.39,<0.9",

        "matplotlib>=3.8,<3.11",
        "plotly>=5.20,<6.0",
        "umap-learn>=0.5.6,<0.6",

        "pca==2.0.9",
        "kneed==0.8.5",
        "pdfplumber==0.11.5",

        # --- Cluster natural-report optimization ---
        "bayesian-optimization>=3.0.0b1,<4.0",

        # # Fix pkg_resources
        # "setuptools<81",
    ],
    python_requires=">=3.11",
    entry_points={
        "console_scripts": [
            "almos=almos.almos:main",
            "cluster=almos.almos:main",
            "al=almos.almos:main",
            "almos-cluster=almos.almos:main",
            "almos-al=almos.almos:main",
        ],
        "gui_scripts": [
            "easyalmos=almos.easyalmos:main",
        ],
    },
    include_package_data=True,
)
