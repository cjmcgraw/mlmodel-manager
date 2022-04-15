import setuptools
setuptools.setup(
    name="model_manager_lib",
    version="0.0.1",
    packages=["model_manager_lib"],
    install_requires=[
        "tensorflow-serving-api==2.5.1",
        "grpcio==1.39.0",
        "grpcio-tools==1.39.0",
    ]
)
