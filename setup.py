from setuptools import setup, find_packages
version = "0.1.0"
setup(
    name="almos",
    packages=find_packages(exclude=["tests"]),
    package_data={"almos": ["templates/*"]},
    version=version,
    license="MIT",
    description="Active Learning Molecular Selection",
    long_description="Documentation in Read The Docs: https://almos.readthedocs.io",
    long_description_content_type="text/markdown",
    author="Miguel Martínez Fernández, Susana P. García Abellán, Juan V. Alegre Requena",
    author_email="miguel.martinez@csic.es",
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
        "Development Status :: 3 - Production/Stable",  # Chose either "3 - Alpha", "4 - Beta" or "5 - Production/Stable" as the current state of your package
        "Intended Audience :: Developers",  # Define that your audience are developers
        "Topic :: Software Development :: Build Tools",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    install_requires=[
        "almos==0.1.0",
        "robert==1.2.2",
        "plotly==5.24.1",
        "pca==2.0.7"
    ],
    python_requires=">=3.10",
    include_package_data=True,
    )