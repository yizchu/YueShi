from setuptools import setup, find_packages

setup(
    name="edu-eval",
    version="0.1.0",
    packages=find_packages(),
    include_package_data=True,
    package_data={"edu_eval": ["prompts/*.md"]},
    install_requires=[
        "openai",
        "pyyaml",
        "fastapi>=0.110",
        "uvicorn>=0.26",
    ],
)