import io
import os

from setuptools import find_packages, setup

with open("README.md", "r") as f:
    long_description = f.read()

pkgname = 'mumot'

version_namespace = {}
here = os.path.abspath(os.path.dirname(__file__))
with io.open(os.path.join(here, pkgname, '_version.py'), encoding='utf8') as f:
    exec(f.read(), {}, version_namespace)


setup(
    name=pkgname,
    description='Multiscale Modelling Tool',
    version=version_namespace['__version__'],
    author='James A. R. Marshall, Andreagiovanni Reina, Thomas Bose',
    author_email='james.marshall@shef.ac.uk',
    long_description=long_description,
    long_description_content_type="text/markdown",
    url='https://github.com/DiODeProject/MuMoT',
    packages=find_packages(),
    package_dir={'': '.'},
    package_data={'mumot.gen': ['PS.tokens', 'PSLexer.tokens']},
    license='GPL-3.0',
    install_requires=[
<<<<<<< Updated upstream
        'antlr4-python3-runtime==4.5.3',
        'graphviz',
        'ipython',
        'ipywidgets',
=======
        # 'alabaster==0.7.11',
        # 'antlr4-python3-runtime==4.5.3',
        # 'atomicwrites==1.1.5',
        # 'attrs==18.1.0',
        # 'Babel==2.6.0',
        # 'bleach==2.0.0',
        # 'certifi==2018.4.16',
        # 'chardet==3.0.4',
        # 'colorama==0.3.9',
        # 'coverage==4.5.1',
        # 'cycler==0.10.0',
        # 'decorator==4.1.2',
        # 'docutils==0.14',
        # 'entrypoints==0.2.3',
        # 'fastcache==1.0.2',
        # 'gitdb2==2.0.4',
        # 'GitPython==2.1.11',
        # 'gmpy2==2.0.8',
        # 'graphviz==0.8.2',
        # 'html5lib==1.0.1',
        # 'idna==2.7',
        # 'imagesize==1.0.0',
        # 'ipykernel==4.6.1',
        # 'ipython==6.2.1',
        # 'ipython-genutils==0.2.0',
        # 'ipywidgets==7.0.5',
        # 'jedi==0.11.1',
        # 'Jinja2==2.10',
        # 'jsonschema==2.6.0',
        # 'jupyter==1.0.0',
        # 'jupyter-client==5.2.2',
        # 'jupyter-console==5.2.0',
        # 'jupyter-contrib-core==0.3.3',
        # 'jupyter-contrib-nbextensions==0.5.0',
        # 'jupyter-core==4.4.0',
        # 'jupyter-highlight-selected-word==0.1.1',
        # 'jupyter-latex-envs==1.4.4',
        # 'jupyter-nbextensions-configurator==0.4.0',
        # 'lxml==4.2.1',
        # 'MarkupSafe==1.0',
        # 'matplotlib==2.0.2',
        # 'mistune==0.8.3',
        # 'more-itertools==4.3.0',
        # 'mpmath==0.19',
        # 'nbconvert==5.3.1',
        # 'nbdime==1.0.2',
        # 'nbformat==4.4.0',
        # 'nbval==0.9.1',
        # 'networkx==1.11',
        # 'notebook==5.4.0',
        # 'numpy==1.13.1',
        # 'packaging==17.1',
        # 'pandocfilters==1.4.1',
        # 'parso==0.1.1',
        # 'path.py==11.0.1',
        # 'pathlib2==2.3.2',
        # 'pexpect==4.3.1',
        # 'pickleshare==0.7.4',
        # 'pluggy==0.7.1',
        # 'prompt-toolkit==1.0.15',
        # 'ptyprocess==0.5.2',
        # 'py==1.5.4',
        # 'PyDSTool==0.90.2',
        # 'Pygments==2.2.0',
        # 'pyparsing==2.2.0',
        # 'pytest==3.7.1',
        # 'pytest-cov==2.5.1',
        # 'python-dateutil==2.6.1',
        # 'pytz==2017.2',
        # 'PyYAML==3.12',
        # 'pyzmq==16.0.2',
        # 'qtconsole==4.3.1',
        # 'requests==2.19.1',
        # 'scipy==0.19.1',
        # 'Send2Trash==1.4.2',
        # 'simplegeneric==0.8.1',
        # 'six==1.10.0',
        # 'smmap2==2.0.4',
        # 'snowballstemmer==1.2.1',
        # 'Sphinx==1.7.6',
        # 'sphinx-rtd-theme==0.4.1',
        # 'sphinxcontrib-websupport==1.1.0',
        # 'sympy==1.1.1',
        # 'terminado==0.8.1',
        # 'testpath==0.3',
        # 'tornado==4.5.3',
        # 'traitlets==4.3.2',
        # 'urllib3==1.23',
        # 'wcwidth==0.1.7',
        # 'webencodings==0.5',
        # 'widgetsnbextension==3.0.8'
        'antlr4-python3-runtime==4.5.3',
        'graphviz',
>>>>>>> Stashed changes
        'matplotlib<3.0',  # see https://github.com/DiODeProject/MuMoT/issues/171
        'networkx',
        'pydstool',
        'scipy<1.0.0',  # see https://github.com/DiODeProject/MuMoT/issues/63
<<<<<<< Updated upstream
        'sympy >= 1.1.1, < 1.3'  # see https://github.com/DiODeProject/MuMoT/issues/170
=======
        'sympy >= 1.1.1, < 1.3',  # see https://github.com/DiODeProject/MuMoT/issues/170
#        'ipykernel==4.6.1', # see https://github.com/DiODeProject/MuMoT/issues/158 for this and following dependencies
#        'ipython==6.2.1',
#        'ipython-genutils==0.2.0',
#        'ipywidgets==7.0.5',
#        'jupyter==1.0.0',
#        'jupyter-client==5.2.2',
#        'jupyter-console==5.2.0',
#        'jupyter-contrib-core==0.3.3',
#        'jupyter-contrib-nbextensions==0.5.0',
#        'jupyter-core==4.4.0',
#        'matplotlib==2.0.2',
#        'notebook==5.4.0',
#        'tornado==4.5.3',
#        'widgetsnbextension==3.0.8'
>>>>>>> Stashed changes
        ],
    extras_require={
        'test': [
            'pytest',
            'pytest-cov',
            'nbval',
            'nbdime',
            'jupyter',
            ],
        'docs': [
            'sphinx',
        ],
    },
    classifiers=[
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Topic :: Scientific/Engineering",
        "Topic :: Scientific/Engineering :: Chemistry",
        "Topic :: Scientific/Engineering :: Mathematics",
        "Topic :: Scientific/Engineering :: Physics",
        ],
)
