from setuptools import setup
setup(
    name = 'platform_cli',
    version = '1.0.13',
    packages = ['platform_cli'],
    install_requires = [
        'psutil >= 0.6.1',
        'pystache >= 0.5.3',
        'clint >= 0.3.1',
    ]
)
