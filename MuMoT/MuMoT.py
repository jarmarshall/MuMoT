""" @package MuMoT
# coding: utf-8

# In[ ]:

# if has extension .ipynb build this notebook as an importable module using
# ipython nbconvert --to script MuMoT.ipynb

# dependencies:
#  tex distribution
#  libtool (on Mac: brew install libtool --universal; brew link libtool (http://brew.sh))
#  antlr4 (for generating LaTeX parser; http://www.antlr.org)
#  latex2sympy (no current pip installer; https://github.com/augustt198/latex2sympy; depends on antlr4 (pip install antlr4-python3-runtime)
#  graphviz (pip install graphviz; graphviz http://www.graphviz.org/Download.php)
"""

from IPython.display import display, clear_output, Math, Latex, Javascript
import ipywidgets.widgets as widgets
from matplotlib import pyplot as plt
import matplotlib.cm as cm
import matplotlib.patches as mpatch
import numpy as np
from scipy.integrate import odeint
from sympy import *
import math
import PyDSTool as dst
from graphviz import Digraph
from process_latex.process_latex import process_sympy # was `from process_latex import process_sympy` before packaging for pip
import tempfile
import os
import copy
from pyexpat import model
from idlelib.textView import view_file
from IPython.utils import io
import datetime
import warnings
from matplotlib.cbook import MatplotlibDeprecationWarning
from mpl_toolkits.mplot3d import axes3d
import networkx as nx #@UnresolvedImport
from enum import Enum
import json
import sys

import matplotlib.ticker as ticker
from math import log10, floor
import ast
from matplotlib.pyplot import plot

#from matplotlib.offsetbox import kwargs
#from __builtin__ import None
#from numpy.oldnumeric.fix_default_axis import _args3
#from matplotlib.offsetbox import kwargs



get_ipython().magic('alias_magic model latex')
get_ipython().magic('matplotlib nbagg')

figureCounter = 1 # global figure counter for model views

MAX_RANDOM_SEED = 4294967295
INITIAL_RATE_VALUE = 0.5
RATE_BOUND = 10.0
RATE_STEP = 0.1
MULTIPLOT_COLUMNS = 2

INITIAL_COND_INIT_VAL = 0.0
INITIAL_COND_INIT_BOUND = 1.0


line_color_list = ['b', 'g', 'r', 'c', 'm', 'y', 'grey', 'orange', 'k']

# enum possible Network types
class NetworkType(Enum):
    FULLY_CONNECTED = 0
    ERSOS_RENYI = 1
    BARABASI_ALBERT = 2
    SPACE = 3
    DYNAMIC = 4

# class with default parameters
class MuMoTdefault:
    _initialRateValue = 2 ## @todo: was 1 (choose initial values sensibly)
    _rateLimits = (0.0, 20.0) ## @todo: choose limit values sensibly
    _rateStep = 0.1 ## @todo: choose rate step sensibly
    @staticmethod
    def setRateDefaults(initRate=_initialRateValue, limits=_rateLimits, step=_rateStep):
        MuMoTdefault._initialRateValue = initRate
        MuMoTdefault._rateLimits = limits
        MuMoTdefault._rateStep = step
    
    _maxTime = 10
    _timeLimits = (1, 100)
    _timeStep = 1
    @staticmethod
    def setTimeDefaults(initTime=_maxTime, limits=_timeLimits, step=_timeStep):
        MuMoTdefault._maxTime = initTime
        MuMoTdefault._timeLimits = limits
        MuMoTdefault._timeStep = step
        
    _agents = 100
    _agentsLimits = (0, 1000)
    _agentsStep = 1
    @staticmethod
    def setAgentsDefaults(initAgents=_agents, limits=_agentsLimits, step=_agentsStep):
        MuMoTdefault._agents = initAgents
        MuMoTdefault._agentsLimits = limits
        MuMoTdefault._agentsStep = step
    

## class describing a model
class MuMoTmodel:
    ## list of rules
    _rules = None 
    ## set of reactants
    _reactants = None
    ## set of fixed-concentration reactants (boundary conditions)
    _constantReactants = None 
    ## parameter that determines system size, set by using substitute()
    _systemSize = None
    ## is system size constant or not?
    _constantSystemSize = None
    ## list of LaTeX strings describing reactants (@todo: depracated?)
    _reactantsLaTeX = None
    ## set of rates
    _rates = None 
    ## dictionary of LaTeX strings describing rates and constant reactants (@todo: rename)
    _ratesLaTeX = None 
    ## dictionary of ODE righthand sides with reactant as key
    _equations = None
    ## set of solutions to equations
    _solutions = None 
    ## summary of stoichiometry as nested dictionaries
    _stoichiometry = None
    ## dictionary of lambdified functions for integration, plotting, etc.
    _funcs = None
    ## tuple of argument symbols for lambdified functions
    _args = None 
    ## graphviz visualisation of model
    _dot = None
    ## image format used for rendering edge labels for model visualisation
    _renderImageFormat = 'png'
    ## local path for creation of temporary storage
    _tmpdirpath = '__mumot_files__'
    ## temporary storage for image files, etc. used in visualising model
    _tmpdir = None 
    ## list of temporary files created
    _tmpfiles = None 
    
    ## create new model with variable substitutions listed as comma separated string of assignments
    def substitute(self, subsString):
        subs = []
        subsStrings = subsString.split(',')
        for subString in subsStrings:
            if '=' not in subString:
                raise SyntaxError("No '=' in assignment " + subString)
            assignment = process_sympy(subString)
            subs.append((assignment.lhs, assignment.rhs))
        newModel = MuMoTmodel()
        newModel._rules = copy.deepcopy(self._rules)
        newModel._reactants = copy.deepcopy(self._reactants)
        newModel._constantReactants = copy.deepcopy(self._constantReactants)
        newModel._equations = copy.deepcopy(self._equations)
        newModel._stoichiometry = copy.deepcopy(self._stoichiometry)
        for sub in subs:
            if sub[0] in newModel._reactants and len(sub[1].atoms(Symbol)) == 1:
                raise SyntaxError("Using substitute to rename reactants not supported: " + str(sub[0]) + " = " + str(sub[1]))
        for reaction in newModel._stoichiometry:
            for sub in subs:
                newModel._stoichiometry[reaction]['rate'] = newModel._stoichiometry[reaction]['rate'].subs(sub[0], sub[1])
                for reactant in newModel._stoichiometry[reaction]:
                    if not reactant == 'rate':
                        if reactant == sub[0]:
                            if '+' not in str(sub[1]) and '-' not in str(sub[1]):
                                #replace keys according to: dictionary[new_key] = dictionary.pop(old_key)
                                newModel._stoichiometry[reaction][sub[1]] = newModel._stoichiometry[reaction].pop(reactant)
                            else:
                                newModel._stoichiometry[reaction][reactant].append({reactant: sub[1]})
        for reactant in newModel._reactants:
            for sub in subs:
                newModel._equations[reactant] = newModel._equations[reactant].subs(sub[0], sub[1])
        for rule in newModel._rules:
            for sub in subs:
                rule.rate = rule.rate.subs(sub[0], sub[1])
        for sub in subs:
            if sub[0] in newModel._reactants:
                for atom in sub[1].atoms(Symbol):
                    if atom not in newModel._reactants and atom != self._systemSize:
                        if newModel._systemSize == None:
                            newModel._systemSize = atom
                        else:
                            raise SyntaxError("More than one unknown reactant encountered when trying to set system size: " + str(sub[0]) + " = " + str(sub[1]))
                if newModel._systemSize == None:
                    raise SyntaxError("Expected to find system size parameter but failed: " + str(sub[0]) + " = " + str(sub[1]))
                ## @todo: more thorough error checking for valid system size expression
                newModel._reactants.discard(sub[0])
                del newModel._equations[sub[0]]
        if newModel._systemSize == None:
            newModel._systemSize = self._systemSize
        for reactant in newModel._equations:
            rhs = newModel._equations[reactant]
            for symbol in rhs.atoms(Symbol):
                if symbol not in newModel._reactants and symbol != newModel._systemSize:
                    newModel._rates.add(symbol)
        newModel._ratesLaTeX = {}
        rates = map(latex, list(newModel._rates))
        for (rate, latexStr) in zip(newModel._rates, rates):
            newModel._ratesLaTeX[repr(rate)] = latexStr
        constantReactants = map(latex, list(newModel._constantReactants))
        for (reactant, latexStr) in zip(newModel._constantReactants, constantReactants):
            newModel._ratesLaTeX[repr(reactant)] = '(' + latexStr + ')'

        ## @todo: what else should be copied to new model?

        return newModel


    ## build a graphical representation of the model
    # if result cannot be plotted check for installation of libltdl - eg on Mac see if XQuartz requires update or do:<br>
    #  `brew install libtool --universal` <br>
    #  `brew link libtool`
    def visualise(self):
        errorShown = False
        if self._dot == None:
            dot = Digraph(comment = "Model", engine = 'circo')
            if not self._constantSystemSize:
                dot.node(str('1'), " ", image = self._localLaTeXimageFile(Symbol('\\emptyset'))) ## @todo: only display if used: for now, guess it is used if system size is non-constant                
            for reactant in self._reactants:
                dot.node(str(reactant), " ", image = self._localLaTeXimageFile(reactant))
            for reactant in self._constantReactants:
                dot.node(str(reactant), " ", image = self._localLaTeXimageFile(Symbol(self._ratesLaTeX[repr(reactant)])))                
            for rule in self._rules:
                # render LaTeX representation of rule
                localfilename = self._localLaTeXimageFile(rule.rate)
                htmlLabel = r'<<TABLE BORDER="0"><TR><TD><IMG SRC="' + localfilename + r'"/></TD></TR></TABLE>>'
                if len(rule.lhsReactants) == 1:
                    dot.edge(str(rule.lhsReactants[0]), str(rule.rhsReactants[0]), label = htmlLabel)
                elif len(rule.lhsReactants) == 2:
                    # work out source and target of edge, and arrow syle
                    source = None
                    if rule.rhsReactants[0] == rule.rhsReactants[1]:
                        if rule.rhsReactants[0] == rule.lhsReactants[0] or rule.rhsReactants[0] == rule.lhsReactants[1]:
                            # 'recruited switching' motif A + B -> A + A
                            target = str(rule.rhsReactants[0])
                            head = 'normal'
                            tail = 'dot'
                            direction = 'both'
                            if rule.lhsReactants[0] != rule.rhsReactants[0]:
                                source = str(rule.lhsReactants[0])
                            elif rule.lhsReactants[1] != rule.rhsReactants[0]:
                                source = str(rule.lhsReactants[1])
                    else:
                        for i in range(0,2):
                            if rule.rhsReactants[i] != rule.lhsReactants[0] and rule.rhsReactants[i] != rule.lhsReactants[1]:
                                # one of these _reactants is not like the others... found it
                                if rule.rhsReactants[1 - i] == rule.lhsReactants[0]:
                                    # 'targeted inhibition' motif A + B -> C + A
                                    source = str(rule.lhsReactants[0])
                                    target = str(rule.lhsReactants[1])
                                elif rule.rhsReactants[1 - i] == rule.lhsReactants[1]:
                                    # 'targeted inhibition' motif A + B -> C + B
                                    source = str(rule.lhsReactants[1])
                                    target = str(rule.lhsReactants[0])
                        head = 'dot'
                        tail = 'none'

                    if source == None:
                        # 'reciprocal inhibition' motif A + B -> C + C/D
                        source = str(rule.lhsReactants[0])
                        target = str(rule.lhsReactants[1])
                        head = 'dot'
                        tail = 'dot'

                    if source != None:
                        dot.edge(source, target, label = htmlLabel, arrowhead = head, arrowtail = tail, dir = 'both')
                else:
                    if not errorShown:
                        errorShown = True
                        print("Model contains rules with three or more reactants; only displaying unary and binary rules")
            self._dot = dot
                
        return self._dot

    ## show a sorted LaTeX representation of the model's constant reactants
    def showConstantReactants(self):
        for reactant in self._constantReactants:
            display(Math(self._ratesLaTeX[repr(reactant)]))
#         if self._constantReactantsLaTeX == None:
#             self._constantReactantsLaTeX = []
#             reactants = map(latex, list(self._constantReactants))
#             for reactant in reactants:
#                 self._constantReactantsLaTeX.append(reactant)
#             self._constantReactantsLaTeX.sort()
#         for reactant in self._constantReactantsLaTeX:
#             display(Math(reactant))
        #reactant_list = []
        #for reaction in self._stoichiometry:
        #    for reactant in self._stoichiometry[reaction]:
        #        if not reactant in reactant_list:
        #            if not reactant == 'rate':
        #                display(Math(latex(reactant)))
        #                reactant_list.append(reactant)


    ## show a sorted LaTeX representation of the model's reactants
    def showReactants(self):
        if self._reactantsLaTeX == None:
            self._reactantsLaTeX = []
            reactants = map(latex, list(self._reactants))
            for reactant in reactants:
                self._reactantsLaTeX.append(reactant)
            self._reactantsLaTeX.sort()
        for reactant in self._reactantsLaTeX:
            display(Math(reactant))
        #reactant_list = []
        #for reaction in self._stoichiometry:
        #    for reactant in self._stoichiometry[reaction]:
        #        if not reactant in reactant_list:
        #            if not reactant == 'rate':
        #                display(Math(latex(reactant)))
        #                reactant_list.append(reactant)

    ## show a sorted LaTeX representation of the model's rate parameters
    def showRates(self):
        for reaction in self._stoichiometry:
            out = latex(self._stoichiometry[reaction]['rate']) + "\; (" + latex(reaction) + ")"
            display(Math(out))        
    
    def showRatesOLD(self):
        for rate in self._ratesLaTeX:
            display(Math(self._ratesLaTeX[rate]))

    
    ## show a LaTeX representation of the model system of ODEs
    def showODEs(self):
        for reactant in self._reactants:
            out = "\\displaystyle \\frac{\\textrm{d}" + latex(reactant) + "}{\\textrm{d}t} := " + latex(self._equations[reactant])
            display(Math(out))
    
    ## displays stoichiometry as a dictionary with keys ReactionNr,
    # ReactionNr represents another dictionary with reaction rate, reactants and their stoichiometry
    def showStoichiometry(self):
        out = latex(self._stoichiometry)
        display(Math(out))
    
    ## displays Master equation expressed with ladder operators
    def showMasterEquation(self):
        P, t = symbols('P t')
        out_rhs=""
        stoich = self._stoichiometry
        nvec = []
        for key1 in stoich:
            for key2 in stoich[key1]:
                if not key2 == 'rate':
                    if not key2 in nvec:
                        nvec.append(key2)
        nvec = sorted(nvec, key=default_sort_key)
        assert (len(nvec)==2 or len(nvec)==3 or len(nvec)==4), 'This module works for 2, 3 or 4 different reactants only'
        rhs_dict, substring = _deriveMasterEquation(stoich)
        #rhs_ME = 0
        term_count = 0
        for key in rhs_dict:
            #rhs_ME += terms_gcd(key*(rhs_dict[key][0]-1)*rhs_dict[key][1]*rhs_dict[key][2], deep=True)
            if term_count == 0:
                rhs_plus = ""
            else:
                rhs_plus = " + "
            out_rhs += rhs_plus + latex(rhs_dict[key][3]) + " ( " + latex((rhs_dict[key][0]-1)) + " ) " +  latex(rhs_dict[key][1]) + latex(rhs_dict[key][2])
            term_count += 1
        if len(nvec)==2:
            lhs_ME = Derivative(P(nvec[0], nvec[1],t),t)
        elif len(nvec)==3:
            lhs_ME = Derivative(P(nvec[0], nvec[1], nvec[2], t), t)
        else:
            lhs_ME = Derivative(P(nvec[0], nvec[1], nvec[2], nvec[3], t), t)     
        
        #return {lhs_ME: rhs_ME}
        out = latex(lhs_ME) + ":= " + out_rhs
        display(Math(out))
        if not substring == None:
            for sub in substring:
                display(Math("With \; substitution:\;" + latex(sub) + ":= " + latex(substring[sub])))
        
    ## shows van Kampen expansion when the operators are expanded up to second order
    def showVanKampenExpansion(self):
        rhs_vke, lhs_vke, substring = _doVanKampenExpansion(_deriveMasterEquation, self._stoichiometry)
        out = latex(lhs_vke) + " := \n" + latex(rhs_vke)
        display(Math(out))
        if not substring == None:
            for sub in substring:
                display(Math("With \; substitution:\;" + latex(sub) + ":= " + latex(substring[sub])))
    
    ## shows ODEs derived from the leading term in van Kampen expansion
    def showODEs_vKE(self):
        ODEdict = _getODEs_vKE(_get_orderedLists_vKE, self._stoichiometry)
        for ode in ODEdict:
            out = latex(ode) + " := " + latex(ODEdict[ode])
            display(Math(out))
        
    ## shows Fokker-Planck equation derived from term ~ O(1) in van Kampen expansion
    # this is the linear noise approximation
    def showFokkerPlanckEquation(self):
        FPEdict, substring = _getFokkerPlanckEquation(_get_orderedLists_vKE, self._stoichiometry)
        for fpe in FPEdict:
            out = latex(fpe) + " := " + latex(FPEdict[fpe])
            display(Math(out))
            if not substring == None:
                for sub in substring:
                    display(Math("With \; substitution:\;" + latex(sub) + ":= " + latex(substring[sub])))
    
    ## displays equations of motion of first and second order moments of noise                
    def showNoiseEOM(self):
        EQsys1stOrdMom, EOM_1stOrderMom, NoiseSubs1stOrder, EQsys2ndOrdMom, EOM_2ndOrderMom, NoiseSubs2ndOrder= _getNoiseEOM(_getFokkerPlanckEquation, _get_orderedLists_vKE, self._stoichiometry)
        for eom1 in EOM_1stOrderMom:
            out = "\\displaystyle \\frac{\\textrm{d}" + latex(eom1.subs(NoiseSubs1stOrder)) + "}{\\textrm{d}t} := " + latex(EOM_1stOrderMom[eom1].subs(NoiseSubs1stOrder))
            display(Math(out))
        for eom2 in EOM_2ndOrderMom:
            out = "\\displaystyle \\frac{\\textrm{d}" + latex(eom2.subs(NoiseSubs2ndOrder)) + "}{\\textrm{d}t} := " + latex(EOM_2ndOrderMom[eom2].subs(NoiseSubs2ndOrder))
            display(Math(out))
    
    ## displays noise in the stationary state
    def showNoiseStationarySol(self):
        SOL_1stOrderMom, NoiseSubs1stOrder, SOL_2ndOrdMomDict, NoiseSubs2ndOrder = _getNoiseStationarySol(_getNoiseEOM, _getFokkerPlanckEquation, _get_orderedLists_vKE, self._stoichiometry)
        print('Stationary solutions of first and second order moments of noise:')
        for sol1 in SOL_1stOrderMom:
            out = latex(sol1.subs(NoiseSubs1stOrder)) + latex(r'(t \to \infty)') + ":= " + latex(SOL_1stOrderMom[sol1].subs(NoiseSubs1stOrder))
            display(Math(out))
        for sol2 in SOL_2ndOrdMomDict:
            out = latex(sol2.subs(NoiseSubs2ndOrder)) + latex(r'(t \to \infty)') + " := " + latex(SOL_2ndOrdMomDict[sol2].subs(NoiseSubs2ndOrder))
            display(Math(out))     
        
        
        
    
    # show a LaTeX representation of the model <br>
    # if rules have | after them update notebook (allegedly, or switch browser): <br>
    # `pip install --upgrade notebook`
    def show(self):
        for rule in self._rules:
            out = ""
            for reactant in rule.lhsReactants:
                if type(reactant) is numbers.One:
                    reactant = Symbol('\emptyset')
                if reactant in self._constantReactants:
                    out += "(" 
                out += latex(reactant)
                if reactant in self._constantReactants:
                    out += ")"                 
                out += " + "
            out = out[0:len(out) - 2] # delete the last ' + '
            out += " \\xrightarrow{" + latex(rule.rate) + "}"
            for reactant in rule.rhsReactants:
                if type(reactant) is numbers.One:
                    reactant = Symbol('\emptyset')
                if reactant in self._constantReactants:
                    out += "(" 
                out += latex(reactant)
                if reactant in self._constantReactants:
                    out += ")"                 
                out += " + "
            out = out[0:len(out) - 2] # delete the last ' + '
            display(Math(out))


    ## construct interactive time evolution plot for state variables      
    def numSimStateVar(self, stateVariable1, stateVariable2, stateVariable3 = None, stateVariable4 = None, **kwargs):
        try:
            kwargs['showInitSV'] = True
            
            # construct controller
            viewController = self._controller(False, **kwargs)
            
            # construct view
            modelView = MuMoTtimeEvoStateVarView(self, viewController, stateVariable1, stateVariable2, stateVariable3, stateVariable4, **kwargs)
                    
            viewController.setView(modelView)
            viewController._setReplotFunction(modelView._plot_NumSolODE)         
            
            return viewController
        
        except:
            return None

    
    ## construct interactive plot of noise around fixed points        
    def fixedPointNoise(self, stateVariable1, stateVariable2, stateVariable3=None, **kwargs):
        if self._check_state_variables(stateVariable1, stateVariable2, stateVariable3):
            
            kwargs['showNoise'] = True
            n1, n2, n3, n4 = _getNoiseStationarySol(_getNoiseEOM, _getFokkerPlanckEquation, _get_orderedLists_vKE, self._stoichiometry)
            # n3 is second order solution and will be used by MuMoTnoiseView
            
            
            # get stationary solution of moments of noise variables <eta_i> and <eta_i eta_j>
            #noiseStatSol = (n1,n2,n3,n4)#_getNoiseStationarySol(_getNoiseEOM, _getFokkerPlanckEquation, _get_orderedLists_vKE, self._stoichiometry)
            
            # construct controller
            viewController = self._controller(False, plotLimitsSlider = not(self._constantSystemSize), **kwargs)
            #viewController = self._controller(True, plotLimitsSlider = True, **kwargs)
            
            # construct view
            modelView = MuMoTnoiseView(self, viewController, n3, stateVariable1, stateVariable2, **kwargs)
                    
            viewController.setView(modelView)
            viewController._setReplotFunction(modelView._plot_field)         
            
            return viewController
        else:
            return None



    ## construct interactive stream plot        
    def stream(self, stateVariable1, stateVariable2, stateVariable3 = None, **kwargs):
        if self._check_state_variables(stateVariable1, stateVariable2, stateVariable3):
            if stateVariable3 != None:
                print("3d stream plots not currently supported")
                
                return None
            # construct controller
            viewController = self._controller(True, plotLimitsSlider = not(self._constantSystemSize), **kwargs)
            
            # construct view
            modelView = MuMoTstreamView(self, viewController, stateVariable1, stateVariable2, **kwargs)
                    
            viewController.setView(modelView)
            viewController._setReplotFunction(modelView._plot_field)         
            
            return viewController
        else:
            return None

    ## construct interactive vector plot        
    def vector(self, stateVariable1, stateVariable2, stateVariable3 = None, **kwargs):
        if self._check_state_variables(stateVariable1, stateVariable2, stateVariable3):
            # construct controller
            viewController = self._controller(True, plotLimitsSlider = not(self._constantSystemSize), **kwargs)
            
            # construct view
            modelView = MuMoTvectorView(self, viewController, stateVariable1, stateVariable2, stateVariable3, **kwargs)
                    
            viewController.setView(modelView)
            viewController._setReplotFunction(modelView._plot_field)         
                        
            return viewController
        else:
            return None
        
    ## construct interactive PyDSTool plot
    def bifurcation(self, bifurcationParameter, stateVariable1, stateVariable2 = None, **kwargs):
        if self._systemSize != None:
            pass
        else:
            print('Cannot construct bifurcation plot until system size is set, using substitute()')
            return    

        initialRateValue = INITIAL_RATE_VALUE ## @todo was 1 (choose initial values sensibly)
        rateLimits = (0, RATE_BOUND) ## @todo choose limit values sensibly
        rateStep = RATE_STEP ## @todo choose rate step sensibly                


        # construct controller
        paramValues = []
        paramNames = []        
        for rate in self._rates:
            if str(rate) != bifurcationParameter:
                paramValues.append((initialRateValue, rateLimits[0], rateLimits[1], rateStep))
                paramNames.append(str(rate))
        viewController = MuMoTcontroller(paramValues, paramNames, self._ratesLaTeX, False, **kwargs)

        # construct view
        modelView = MuMoTbifurcationView(self, viewController, bifurcationParameter, stateVariable1, stateVariable2, **kwargs)
        
        viewController.setView(modelView)
        viewController._setReplotFunction(modelView._replot_bifurcation)
        
        return viewController

    def multiagent(self, netType="full", initialState="Auto", maxTime="Auto", randomSeed="Auto", **kwargs):
        MAParams = {}
        if initialState=="Auto":
            first = True
            initialState = {}
            for reactant in self._reactants:
                if first:
#                     print("Automatic Initial State sets " + str(MuMoTdefault._agents) + " agents in state " + str(reactant) )
                    initialState[reactant] = MuMoTdefault._agents
                    first = False
                else:
                    initialState[reactant] = 0
        else:
            ## @todo check if the Initial State has valid length and positive values
#             print("TODO: check if the Initial State has valid length and positive values")
#             initialState_str = ast.literal_eval(initialState) # translate string into dict
            initialState_str = initialState
            initialState = {}
            for state,pop in initialState_str.items():
                initialState[process_sympy(state)] = pop # convert string into SymPy symbol
#         print("Initial State is " + str(initialState) )
        MAParams['initialState'] = initialState
        
        # init the max-time
        if (maxTime == "Auto" or maxTime <= 0):
            maxTime = MuMoTdefault._maxTime
        timeLimitMax = max(maxTime, MuMoTdefault._timeLimits[1])
        MAParams["maxTime"] = (maxTime, MuMoTdefault._timeLimits[0], timeLimitMax, MuMoTdefault._timeStep)
        # init the random seed 
        if (randomSeed == "Auto" or randomSeed <= 0 or randomSeed > MAX_RANDOM_SEED):
            randomSeed = np.random.randint(MAX_RANDOM_SEED)
#             print("Automatic Random Seed set to " + str(randomSeed) )
        MAParams['randomSeed'] = randomSeed
        # check validity of the network type
        if _decodeNetworkTypeFromString(netType) == None: return # terminating the process if the input argument is wrong
        MAParams['netType'] = netType
#         print("Network type set to " + str(MAParams['netType']) ) 

        # Setting some default values 
        ## @todo add possibility to customise these values from input line
        MAParams['motionCorrelatedness'] = kwargs.get('motionCorrelatedness', (0.5, 0.0, 1.0, 0.05))
        MAParams['particleSpeed'] = kwargs.get('particleSpeed', (0.01, 0.0, 0.1, 0.005))
        MAParams['visualisationType'] = kwargs.get('visualisationType', 'evo') # default view is time-evolution
        MAParams['timestepSize'] = kwargs.get('timestepSize', (1, 0.01, 1, 0.01) )
        MAParams['showTrace'] = kwargs.get('showTrace', netType == 'dynamic')
        MAParams['showInteractions'] = kwargs.get('showInteractions', False)
        ## realtimePlot flag (TRUE = the plot is updated each timestep of the simulation; FALSE = it is updated once at the end of the simulation)
        MAParams['realtimePlot'] = kwargs.get('realtimePlot', False)
        
        # construct controller
        paramValues = []
        paramNames = [] 
        for rate in self._rates:
            paramValues.append((MuMoTdefault._initialRateValue, MuMoTdefault._rateLimits[0], MuMoTdefault._rateLimits[1], MuMoTdefault._rateStep))
            paramNames.append(str(rate))

        viewController = MuMoTmultiagentController(paramValues, paramNames, self._ratesLaTeX, False, MAParams, **kwargs)
        # Get the default network values assigned from the controller
        MAParams['netParam'] = viewController._widgetsExtraParams['netParam'].value ## @todo use defaults without relying on the controller 
        
        modelView = MuMoTmultiagentView(self, viewController, MAParams, **kwargs)
        viewController.setView(modelView)
#         viewController._setReplotFunction(modelView._plot_timeEvolution(self._reactants, self._rules))
        viewController._setReplotFunction(modelView._plot_timeEvolution, modelView._redrawOnly)

        return viewController

    def SSA(self, initialState="Auto", maxTime="Auto", randomSeed="Auto", **kwargs):
        ssaParams = {}
        if initialState=="Auto":
            first = True
            initialState = {}
            for reactant in self._reactants|self._constantReactants:
                if first:
#                     print("Automatic Initial State sets " + str(MuMoTdefault._agents) + " agents in state " + str(reactant) )
                    initialState[reactant] = MuMoTdefault._agents
                    first = False
                else:
                    initialState[reactant] = 0
        else:
            ## @todo check if the Initial State has valid length and positive values
#             print("TODO: check if the Initial State has valid length and positive values")
#             initialState_str = ast.literal_eval(initialState) # translate string into dict
            initialState_str = initialState
            initialState = {}
            for state,pop in initialState_str.items():
                initialState[process_sympy(state)] = pop # convert string into SymPy symbol
#         print("Initial State is " + str(initialState) )
        ssaParams['initialState'] = initialState
        
        if (maxTime == "Auto" or maxTime <= 0):
            maxTime = MuMoTdefault._maxTime
        timeLimitMax = max(maxTime, MuMoTdefault._timeLimits[1])
        ssaParams["maxTime"] = (maxTime, MuMoTdefault._timeLimits[0], timeLimitMax, MuMoTdefault._timeStep)
        if (randomSeed == "Auto" or randomSeed <= 0 or randomSeed > MAX_RANDOM_SEED):
            randomSeed = np.random.randint(MAX_RANDOM_SEED)
#             print("Automatic Random Seed set to " + str(randomSeed) )
        ssaParams['randomSeed'] = randomSeed
        ssaParams['visualisationType'] = 'evo'
        ssaParams['realtimePlot'] = kwargs.get('realtimePlot', False)
            
        # construct controller
        paramValues = []
        paramNames = [] 
        #paramValues.extend( [initialState, netType, maxTime] )
        for rate in self._rates:
            paramValues.append((MuMoTdefault._initialRateValue, MuMoTdefault._rateLimits[0], MuMoTdefault._rateLimits[1], MuMoTdefault._rateStep))
            paramNames.append(str(rate))

        viewController = MuMoTSSAController(paramValues=paramValues, paramNames=paramNames, paramLabelDict=self._ratesLaTeX, continuousReplot=False, ssaParams=ssaParams, **kwargs)
        #paramDict = {}
        #paramDict['initialState'] = initialState
        modelView = MuMoTSSAView(self, viewController, ssaParams, **kwargs)
        viewController.setView(modelView)
        #modelView._plot_timeEvolution()
        
#         viewController._setReplotFunction(modelView._plot_timeEvolution(self._reactants, self._rules))
        viewController._setReplotFunction(modelView._plot_timeEvolution, modelView._redrawOnly)
        
        return viewController

#         if stateVariable2 == None:
#             # 2-d bifurcation diagram
#             # create widgets
# 
#             if self._systemSize != None:
#                 ## @todo: shouldn't allow system size to be varied?
#                 pass
# #                self._paramValues.append(1)
# #                self._paramNames.append(str(self._systemSize))
# #                widget = widgets.FloatSlider(value = 1, min = _rateLimits[0], max = _rateLimits[1], step = _rateStep, description = str(self._systemSize), continuous_update = False)
# #                widget.on_trait_change(self._replot_bifurcation2D, 'value')
# #                self._widgets.append(widget)
# #                display(widget)
#             else:
#                 print('Cannot attempt bifurcation plot until system size is set, using substitute()')
#                 return
#             for rate in self._rates:
#                 if str(rate) != bifurcationParameter:
#                     self._paramValues.append(_initialRateValue)
#                     self._paramNames.append(str(rate))
#                     widget = widgets.FloatSlider(value = _initialRateValue, min = _rateLimits[0], max = _rateLimits[1], step = _rateStep, description = str(rate), continuous_update = False)
#                     widget.on_trait_change(self._replot_bifurcation2D, 'value')
#                     self._widgets.append(widget)
#                     display(widget)
#             widget = widgets.HTML(value = '')
#             self._errorMessage = widget                                ## @todo: add to __init__()
#             display(self._errorMessage)
#             
#             # Prepare the system to start close to a steady state
#             self._bifurcationParameter = bifurcationParameter          ## @todo: remove hack (bifurcation parameter for multiple possible bifurcations needs to be stored in self)
#             self._stateVariable1 = stateVariable1                      ## @todo: remove hack (state variable for multiple possible bifurcations needs to be stored in self)
# #            self._pyDSode.set(pars = {bifurcationParameter: 0} )       # Lower bound of the bifurcation parameter (@todo: set dynamically)
# #            self._pyDSode.set(pars = self._pyDSmodel.pars )       # Lower bound of the bifurcation parameter (@todo: set dynamically)
# #            self._pyDSode.pars = {bifurcationParameter: 0}             # Lower bound of the bifurcation parameter (@todo: set dynamically?)
#             initconds = {stateVariable1: self._paramDict[str(self._systemSize)] / len(self._reactants)} ## @todo: guess where steady states are?
#             for reactant in self._reactants:
#                 if str(reactant) != stateVariable1:
#                     initconds[str(reactant)] = self._paramDict[str(self._systemSize)] / len(self._reactants)
# #            self._pyDSmodel.ics = initconds
#             self._pyDSmodel.ics      = {'A': 0.1, 'B': 0.9 }    ## @todo: replace            
# #            self._pyDSode.set(ics = initconds)
#             self._pyDSode = dst.Generator.Vode_ODEsystem(self._pyDSmodel)  ## @todo: add to __init__()
#             self._pyDSode.set(pars = {bifurcationParameter: 5} )                       ## @todo remove magic number
#             self._pyDScont = dst.ContClass(self._pyDSode)              # Set up continuation class (@todo: add to __init__())
#             ## @todo: add self._pyDScontArgs to __init__()
#             self._pyDScontArgs = dst.args(name='EQ1', type='EP-C')     # 'EP-C' stands for Equilibrium Point Curve. The branch will be labeled 'EQ1'.
#             self._pyDScontArgs.freepars     = [bifurcationParameter]   # control parameter(s) (should be among those specified in self._pyDSmodel.pars)
#             self._pyDScontArgs.MaxNumPoints = 450                      # The following 3 parameters are set after trial-and-error @todo: how to automate this?
#             self._pyDScontArgs.MaxStepSize  = 1e-1
#             self._pyDScontArgs.MinStepSize  = 1e-5
#             self._pyDScontArgs.StepSize     = 2e-3
#             self._pyDScontArgs.LocBifPoints = ['LP', 'BP']                    ## @todo WAS 'LP' (detect limit points / saddle-node bifurcations)
#             self._pyDScontArgs.SaveEigen    = True                     # to tell unstable from stable branches
# #            self._pyDScontArgs.CalcStab     = True
# 
#             plt.ion()
# #            self._bifurcation2Dfig = plt.figure(1)                     ## @todo: add to __init__()
#             self._pyDScont.newCurve(self._pyDScontArgs)
#             try:
#                 try:
#                     self._pyDScont['EQ1'].backward()
#                 except:
#                     self._errorMessage.value = 'Continuation failure'
#                 try:
#                     self._pyDScont['EQ1'].forward()                                  ## @todo: how to choose direction?
#                 except:
#                     self._errorMessage.value = 'Continuation failure'
#                     self._errorMessage.value = ''
#             except ZeroDivisionError:
#                 self._errorMessage.value = 'Division by zero'
# #            self._pyDScont['EQ1'].info()
#             self._pyDScont.display([bifurcationParameter, stateVariable1], stability = True, figure = 1)
#             self._pyDScont.plot.fig1.axes1.axes.set_title('Bifurcation Diagram')
#         else:
#             # 3-d bifurcation diagram
#             assert false

    def _get_solutions(self):
        if self._solutions == None:
            self._solutions = solve(iter(self._equations.values()), self._reactants, force = False, positive = False, set = False)
        return self._solutions

    ## general controller constructor with all rates as free parameters
    def _controller(self, contRefresh, displayController = True, plotLimitsSlider = False, **kwargs):
        initialRateValue = INITIAL_RATE_VALUE ## @todo was 1 (choose initial values sensibly)
        rateLimits = (0, RATE_BOUND) ## @todo choose limit values sensibly
        rateStep = RATE_STEP ## @todo choose rate step sensibly                

        # construct controller
        paramValues = []
        paramNames = []        
        for rate in self._rates:
            paramValues.append((initialRateValue, rateLimits[0], rateLimits[1], rateStep))
            paramNames.append(str(rate))
        for reactant in self._constantReactants:
            paramValues.append((initialRateValue, rateLimits[0], rateLimits[1], rateStep))
#            paramNames.append('(' + latex(reactant) + ')')
            paramNames.append(str(reactant))
        if kwargs.get('showInitSV', False) == True:
            initialInitCondValue = INITIAL_COND_INIT_VAL
            initialCondLimits = (0, INITIAL_COND_INIT_BOUND)
            for reactant in self._reactants:
                if reactant not in self._constantReactants:
                    paramNames.append(latex(Symbol('Phi^0_'+str(reactant))))
                    paramValues.append((initialInitCondValue, initialCondLimits[0], initialCondLimits[1], rateStep))
            
        systemSizeSlider = kwargs.get('showNoise', False)
        viewController = MuMoTcontroller(paramValues, paramNames, self._ratesLaTeX, contRefresh, plotLimitsSlider, systemSizeSlider, **kwargs)

        return viewController

    def _check_state_variables(self, stateVariable1, stateVariable2, stateVariable3 = None):
        if process_sympy(stateVariable1) in self._reactants and process_sympy(stateVariable2) in self._reactants and (stateVariable3 == None or process_sympy(stateVariable3) in self._reactants):
            if stateVariable1 != stateVariable2 and stateVariable1 != stateVariable3 and stateVariable2 != stateVariable3:
                return True
            else:
                print('State variables cannot be the same')
                return False
        else:
            print('Invalid reactant provided as state variable')
            return False


    ## lambdify sympy equations for numerical integration, plotting, etc.
    def _getFuncs(self):
#         if self._systemSize == None:
#             assert false ## @todo is this necessary?
        if self._funcs == None:
            argList = []
            for reactant in self._reactants:
                argList.append(reactant)
            for reactant in self._constantReactants:
                argList.append(reactant)
            for rate in self._rates:
                argList.append(rate)
            if self._systemSize != None:
                argList.append(self._systemSize)
            self._args = tuple(argList)
            self._funcs = {}
            for equation in self._equations:
                f = lambdify(self._args, self._equations[equation], "math")
                self._funcs[equation] = f
            
        return self._funcs
    
    ## get tuple to evalute functions returned by _getFuncs with, for 2d field-based plots
    def _getArgTuple2d(self, argNames, argValues, argDict, stateVariable1, stateVariable2, X, Y):
        argList = []
        for arg in self._args:
            if arg == stateVariable1:
                argList.append(X)
            elif arg == stateVariable2:
                argList.append(Y)
            elif arg == self._systemSize:
                argList.append(1) ## @todo: system size set to 1
            else:
                argList.append(argDict[arg])
            
        return tuple(argList)

    ## get tuple to evalute functions returned by _getFuncs with, for 2d field-based plots
    def _getArgTuple3d(self, argNames, argValues, argDict, stateVariable1, stateVariable2, stateVariable3, X, Y, Z):
        argList = []
        for arg in self._args:
            if arg == stateVariable1:
                argList.append(X)
            elif arg == stateVariable2:
                argList.append(Y)
            elif arg == stateVariable3:
                argList.append(Z)                
            elif arg == self._systemSize:
                argList.append(1) ## @todo: system size set to 1
            else:
                argList.append(argDict[arg])
            
        return tuple(argList)

    ## get tuple to evalute functions returned by _getFuncs with
    def _getArgTuple(self, argNames, argValues, argDict, reactants, reactantValues):
        assert false # need to work this out
        argList = []
#         for arg in self._args:
#             if arg == stateVariable1:
#                 argList.append(X)
#             elif arg == stateVariable2:
#                 argList.append(Y)
#             elif arg == stateVariable3:
#                 argList.append(Z)                
#             elif arg == self._systemSize:
#                 argList.append(1) ## @todo: system size set to 1
#             else:
#                 argList.append(argDict[arg])
            
        return tuple(argList)


    ## render LaTeX source to local image file                                 
    def _localLaTeXimageFile(self, source):
        tmpfile = tempfile.NamedTemporaryFile(dir = self._tmpdir.name, suffix = '.' + self._renderImageFormat, delete = False)
        self._tmpfiles.append(tmpfile)
        preview(source, euler = False, output = self._renderImageFormat, viewer = 'file', filename = tmpfile.name)

        return tmpfile.name[tmpfile.name.find(self._tmpdirpath):]  

#     def _toHTML(self, label):
#         # DEPRECATED
#         errorLabel = label
#         htmlLabel = r'<<I>'
#         parts = label.split('_')
#         label = parts[0]
#         if label[0] == '\\':
#             label = label.replace('\\','&')
#             label += ';'
# 
#         if len(parts) > 1:
#             subscript = parts[1]
#             if len(parts) > 2:
#                 raise SyntaxError("Nested subscripts not currently supported: " + subscript + " in " + errorLabel)
#                 return
#             if len(subscript) > 1:
#                 if  subscript[0] == '{' and subscript[len(subscript) - 1] == '}':
#                     subscript = subscript[1:-1]
#                     if '{' in subscript or '}' in subscript:
#                         raise SyntaxError("Malformed subscript: {" + subscript + "} in " + errorLabel)
#                         return
#                 else:
#                     raise SyntaxError("Non single-character subscript not {} delimited: " + subscript + " in " + errorLabel)
#                     return
#             htmlLabel += label + "<SUB>" + subscript + "</SUB>" + r'</I>>'
#         else:
#             htmlLabel += label + r'</I>>'
#         
#         return htmlLabel
    

    def __init__(self):
        self._rules = []
        self._reactants = set()
        self._systemSize = None
        self._constantSystemSize = True
        self._reactantsLaTeX = None
        self._rates = set()
        self._ratesLaTeX= None
        self._equations = {}
        self._stoichiometry = {}
        self._pyDSmodel = None
        self._dot = None
        if not os.path.isdir(self._tmpdirpath):
            os.mkdir(self._tmpdirpath)
            os.system('chmod' + self._tmpdirpath + 'u+rwx')
            os.system('chmod' + self._tmpdirpath + 'g-rwx')
            os.system('chmod' + self._tmpdirpath + 'o+rwx')
        self._tmpdir = tempfile.TemporaryDirectory(dir = self._tmpdirpath)
        self._tmpfiles = []
        
    def __del__(self):
        ## @todo: check when this is invoked
        for tmpfile in self._tmpfiles:
            del tmpfile
        del self._tmpdir

## class describing a single reaction rule
class _Rule:
    lhsReactants = []
    rhsReactants = []
    rate = ""
    def __init__(self):
        self.lhsReactants = []
        self.rhsReactants = []
        self.rate = ""

## class describing a controller for a model view
class MuMoTcontroller:
    _view = None
    ## dictionary of LaTeX labels for widgets, with parameter name as key
    _paramLabelDict = None
    ## dictionary of controller widgets only for the free parameters of the model, with parameter name as key
    _widgetsFreeParams = None
    ## dictionary of controller widgets for the special parameters (e.g., simulation length, initial state), with parameter name as key
    _widgetsExtraParams = None
    ## dictionary of controller widgets, with parameter that influence only the plotting and not the computation
    _widgetsPlotOnly = None
    ## replot function widgets have been assigned (for use by MuMoTmultiController)
    _replotFunction = None
    ## widget for simple error messages to be displayed to user during interaction
    _errorMessage = None
    ## plot limits slider widget
    _plotLimitsWidget = None
    ## system size slider widget
    _systemSizeWidget = None    
    ## bookmark button widget
    _bookmarkWidget = None
    ## progress bar @todo: is this best put in base class when it is not always used?
    _progressBar = None
    ## used two progress bars, otherwise the previous cell bar (where controller is created) does not react anymore  @todo: is this best put in base class when it is not always used?
    _progressBar_multi = None 

    def __init__(self, paramValues, paramNames, paramLabelDict = {}, continuousReplot = False, plotLimits = False, systemSize = False, **kwargs):
        silent = kwargs.get('silent', False)
        self._paramLabelDict = paramLabelDict
        self._widgetsFreeParams = {}
        self._widgetsExtraParams = {}
        self._widgetsPlotOnly = {}
        self._silent = kwargs.get('silent', False)
        unsortedPairs = zip(paramNames, paramValues)
        for pair in sorted(unsortedPairs):
            widget = widgets.FloatSlider(value = pair[1][0], min = pair[1][1], 
                                         max = pair[1][2], step = pair[1][3], 
                                         description = r'\(' + self._paramLabelDict.get(pair[0],pair[0]) + r'\)', 
                                         continuous_update = continuousReplot)
            self._widgetsFreeParams[pair[0]] = widget
            if not(self._silent):
                display(widget)
        if plotLimits:
            ## @todo: remove hard coded values and limits
            self._plotLimitsWidget = widgets.FloatSlider(value = 1.0, min = 1.0, 
                                         max = 10.0, step = 0.5, 
                                         description = "Plot limits", 
                                         continuous_update = False)
        if systemSize:
            ## @todo: remove hard coded values and limits
            self._systemSizeWidget = widgets.IntSlider(value = 5, min = 5, 
                                         max = 100, step = 1, 
                                         description = "System size", 
                                         continuous_update = False)  
        
        if not(silent):
            if plotLimits:
                display(self._plotLimitsWidget)
            if systemSize:
                display(self._systemSizeWidget)
        self._bookmarkWidget = widgets.Button(description='', disabled=False, button_style='', tooltip='Paste bookmark to log', icon='bookmark')
        self._bookmarkWidget.on_click(self._print_standalone_view_cmd)
        display(self._bookmarkWidget)

        widget = widgets.HTML()
        widget.value = ''
        self._errorMessage = widget
        if not(self._silent):
            display(self._errorMessage)

    def _print_standalone_view_cmd(self, foo):
        self._view._print_standalone_view_cmd()
        self._errorMessage.value = "Pasted bookmark to log - view with showLogs(tail = True)"
    
    ## set the functions that must be triggered when the widgets are changed.
    ## @param[in]    recomputeFunction    The function to be called when recomputing is necessary 
    ## @param[in]    redrawFunction    The function to be called when only redrawing (relying on previous computation) is sufficient 
    def _setReplotFunction(self, recomputeFunction, redrawFunction=None):
        self._replotFunction = recomputeFunction
        for widget in self._widgetsFreeParams.values():
            widget.on_trait_change(recomputeFunction, 'value')
        for widget in self._widgetsExtraParams.values():
            widget.on_trait_change(recomputeFunction, 'value')
        if self._plotLimitsWidget != None:
            self._plotLimitsWidget.on_trait_change(recomputeFunction, 'value')
        if self._systemSizeWidget != None:
            self._systemSizeWidget.on_trait_change(recomputeFunction, 'value')
        if redrawFunction != None:
            for widget in self._widgetsPlotOnly.values():
                widget.on_trait_change(redrawFunction, 'value')

    def setView(self, view):
        self._view = view

    def showLogs(self, tail = False):
        self._view.showLogs(tail)
        
    def multirun(self, iterations, randomSeeds="Auto", visualisationType="evo", downloadData=False):
        # Creating the progress bar (useful to give user progress status for long executions)
        self._progressBar_multi = widgets.FloatProgress(
            value=0,
            min=0,
            max=iterations,
            step=1,
            description='Loading:',
            bar_style='success', # 'success', 'info', 'warning', 'danger' or ''
            orientation='horizontal'
        )
        display(self._progressBar_multi)
        self._view._visualisationType = visualisationType
        
        # setting the "Auto" value to the random seeds:
        if randomSeeds == "Auto":
            randomSeeds = []
            for _ in range(iterations):
                randomSeeds.append(np.random.randint(MAX_RANDOM_SEED))
            print("Automatic Random Seeds set to " + str(randomSeeds) )
        else: # checking if the length of the randomSeeds list is the same of iterations
            if not len(randomSeeds) == iterations:
                print("ERROR! Invalid randomSeeds value. The randomSeeds must be a integer list with the length = iterations")
                return
            if sum(x < 0 or x > MAX_RANDOM_SEED or not isinstance( x, int ) for x in randomSeeds) > 0:
                print("ERROR! Invalid randomSeeds value. The randomSeeds must be integers between 0 and " + str(MAX_RANDOM_SEED))
                return
        
        dataRes = self._view._multirun(iterations, randomSeeds)
        
        self._progressBar_multi.value = self._progressBar_multi.max
        self._progressBar_multi.description = "Completed 100%:"
        
        if downloadData:
            return self._downloadFile(dataRes)


    def _setErrorWidget(self, errorWidget):
        self._errorMessage = errorWidget
            
    def _downloadFile(self, data_to_download):
        js_download = """
        var csv = '%s';
        
        var filename = 'results.csv';
        var blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
        if (navigator.msSaveBlob) { // IE 10+
            navigator.msSaveBlob(blob, filename);
        } else {
            var link = document.createElement("a");
            if (link.download !== undefined) { // feature detection
                // Browsers that support HTML5 download attribute
                var url = URL.createObjectURL(blob);
                link.setAttribute("href", url);
                link.setAttribute("download", filename);
                link.style.visibility = 'hidden';
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
            }
        }
        """ % str(data_to_download)
        #str(data_to_download) 
        #data_to_download.to_csv(index=False).replace('\n','\\n').replace("'","\'")
        
        return Javascript(js_download)

## class describing a controller for multiagent views
class MuMoTSSAController(MuMoTcontroller):
    
    def __init__(self, paramValues, paramNames, paramLabelDict, continuousReplot, ssaParams, **kwargs):
        MuMoTcontroller.__init__(self, paramValues, paramNames, paramLabelDict, continuousReplot, **kwargs)
        advancedWidgets = []
        
        initialState = ssaParams['initialState']
        for state,pop in initialState.items():
            widget = widgets.IntSlider(value = pop,
                                         min = min(pop, MuMoTdefault._agentsLimits[0]), 
                                         max = max(pop, MuMoTdefault._agentsLimits[1]),
                                         step = MuMoTdefault._agentsStep,
                                         description = "State " + str(state), 
                                         continuous_update = continuousReplot)
            self._widgetsExtraParams['init'+str(state)] = widget
            advancedWidgets.append(widget)
            
        # Max time slider
        maxTime = ssaParams['maxTime']
        widget = widgets.FloatSlider(value = maxTime[0], min = maxTime[1], 
                                         max = maxTime[2], step = maxTime[3], 
                                         description = 'Simulation time:',
                                         disabled=False,
                                         continuous_update = continuousReplot) 
        self._widgetsExtraParams['maxTime'] = widget
        advancedWidgets.append(widget)
        
        # Random seed input field
        widget = widgets.IntText(
            value=ssaParams['randomSeed'],
            description='Random seed:',
            disabled=False
        )
        self._widgetsExtraParams['randomSeed'] = widget
        advancedWidgets.append(widget)
        
        ## Toggle buttons for plotting style 
        plotToggle = widgets.ToggleButtons(
            options=[('Temporal evolution', 'evo'), ('Final distribution', 'final')],
            value = ssaParams['visualisationType'],
            description='Plot:',
            disabled=False,
            button_style='', # 'success', 'info', 'warning', 'danger' or ''
            tooltips=['Population change over time', 'Population distribution in each state at final timestep'],
        #     icons=['check'] * 3
        )
        self._widgetsPlotOnly['visualisationType'] = plotToggle
        advancedWidgets.append(plotToggle)
        
        ## Checkbox for realtime plot update
        widget = widgets.Checkbox(
            value = ssaParams.get('realtimePlot',False),
            description='Runtime plot update',
            disabled = False
        )
        self._widgetsExtraParams['realtimePlot'] = widget
        advancedWidgets.append(widget)
        
        advancedPage = widgets.Box(children=advancedWidgets)
        advancedOpts = widgets.Accordion(children=[advancedPage])
        advancedOpts.set_title(0, 'Advanced options')
        if not self._silent:
            display(advancedOpts)
        
        # Loading bar (useful to give user progress status for long executions)
        self._progressBar = widgets.FloatProgress(
            value=0,
            min=0,
            max=self._widgetsExtraParams['maxTime'].value,
            #step=1,
            description='Loading:',
            bar_style='success', # 'success', 'info', 'warning', 'danger' or ''
            orientation='horizontal'
        )
        if not self._silent:
            display(self._progressBar)
        

## class describing a controller for multiagent views
class MuMoTmultiagentController(MuMoTcontroller):

    def __init__(self, paramValues, paramNames, paramLabelDict, continuousReplot, MAParams, **kwargs):
        MuMoTcontroller.__init__(self, paramValues, paramNames, paramLabelDict, continuousReplot, **kwargs)
        advancedWidgets = []
        
        initialState = MAParams['initialState']
        for state,pop in initialState.items():
            widget = widgets.IntSlider(value = pop,
                                         min = min(pop, MuMoTdefault._agentsLimits[0]), 
                                         max = max(pop, MuMoTdefault._agentsLimits[1]),
                                         step = MuMoTdefault._agentsStep,
                                         description = "State " + str(state), 
                                         continuous_update = continuousReplot)
            self._widgetsExtraParams['init'+str(state)] = widget
            advancedWidgets.append(widget)
        
        # Max time slider
        maxTime = MAParams['maxTime']
        widget = widgets.IntSlider(value = maxTime[0], min = maxTime[1], 
                                         max = maxTime[2], step = maxTime[3], 
                                         description = 'Simulation time:',
                                         disabled=False,
                                         continuous_update = continuousReplot) 
        self._widgetsExtraParams['maxTime'] = widget
        advancedWidgets.append(widget)
        
        ## Network type dropdown selector
        netDropdown = widgets.Dropdown( 
            options=[('Full graph', NetworkType.FULLY_CONNECTED), 
                     ('Erdos-Renyi', NetworkType.ERSOS_RENYI),
                     ('Barabasi-Albert', NetworkType.BARABASI_ALBERT),
                     ## @todo: add network topology generated by random points in space
                     ('Moving particles', NetworkType.DYNAMIC)
                     ],
            description='Network topology:',
            value = _decodeNetworkTypeFromString(MAParams['netType']), 
            disabled=False
        )
        self._widgetsExtraParams['netType'] = netDropdown
        #self._widgets.append(netDropdown)
        netDropdown.on_trait_change(self._update_net_params, 'value')
        advancedWidgets.append(netDropdown)
        
        # Network connectivity slider
        widget = widgets.FloatSlider(value = 0,
                                    min = 0, 
                                    max = 1,
                            description = 'Network connectivity parameter', 
                            continuous_update = continuousReplot,
                            disabled=True
        )
        self._widgetsExtraParams['netParam'] = widget
        advancedWidgets.append(widget)
        
        # Agent speed
        particleSpeed = MAParams['particleSpeed']
        widget = widgets.FloatSlider(value = particleSpeed[0],
                                     min = particleSpeed[1], max = particleSpeed[2], step=particleSpeed[3],
                            description = 'Particle speed', 
                            continuous_update = continuousReplot,
                            disabled=True
        )
        self._widgetsExtraParams['particleSpeed'] = widget
        advancedWidgets.append(widget)
        
        # Random walk correlatedness
        motionCorrelatedness = MAParams['motionCorrelatedness']
        widget = widgets.FloatSlider(value = motionCorrelatedness[0],
                                     min = motionCorrelatedness[1],
                                     max = motionCorrelatedness[2],
                                     step=motionCorrelatedness[3],
                            description = 'Correlatedness of the random walk', 
                            continuous_update = continuousReplot,
                            disabled=True
        )
        self._widgetsExtraParams['motionCorrelatedness'] = widget
        advancedWidgets.append(widget)
        
        # Random seed input field
        widget = widgets.IntText(
            value=MAParams['randomSeed'],
            description='Random seed:',
            disabled=False
        )
        self._widgetsExtraParams['randomSeed'] = widget
        advancedWidgets.append(widget)
        #display(widget)
        
        # Time scaling slider
        timestepSize = MAParams['timestepSize']
        widget =  widgets.FloatSlider(value = timestepSize[0],
                                    min = timestepSize[1], 
                                    max = timestepSize[2],
                                    step = timestepSize[3],
                            description = 'Timestep size', 
                            continuous_update = continuousReplot
        )
        self._widgetsExtraParams['timestepSize'] = widget
        advancedWidgets.append(widget)
        
        ## Toggle buttons for plotting style 
        plotToggle = widgets.ToggleButtons(
            #options={'Temporal evolution' : 'evo', 'Network' : 'graph', 'Final distribution' : 'final'},
            options=[('Temporal evolution','evo'), ('Network','graph'), ('Final distribution', 'final')],
            value = MAParams['visualisationType'],
            description='Plot:',
            disabled=False,
            button_style='', # 'success', 'info', 'warning', 'danger' or ''
            tooltips=['Population change over time', 'Network topology', 'Number of agents in each state at final timestep'],
        #     icons=['check'] * 3
        )
        self._widgetsPlotOnly['visualisationType'] = plotToggle
        advancedWidgets.append(plotToggle)
        
        # Particle display checkboxes
        widget = widgets.Checkbox(
            value = MAParams['showTrace'],
            description='Show particle trace',
            disabled = not (self._widgetsExtraParams['netType'].value == NetworkType.DYNAMIC)
        )
        self._widgetsPlotOnly['showTrace'] = widget
        advancedWidgets.append(widget)
        widget = widgets.Checkbox(
            value = MAParams['showInteractions'],
            description='Show communication links',
            disabled = not (self._widgetsExtraParams['netType'].value == NetworkType.DYNAMIC)
        )
        self._widgetsPlotOnly['showInteractions'] = widget
        advancedWidgets.append(widget)
        
        widget = widgets.Checkbox(
            value = MAParams.get('realtimePlot',False),
            description='Runtime plot update',
            disabled = False
        )
        self._widgetsExtraParams['realtimePlot'] = widget
        advancedWidgets.append(widget)
        
        self._update_net_params()
        
        advancedPage = widgets.Box(children=advancedWidgets)
        advancedOpts = widgets.Accordion(children=[advancedPage])
        advancedOpts.set_title(0, 'Advanced options')
        if not self._silent:
            display(advancedOpts)
        
        # Loading bar (useful to give user progress status for long executions)
        self._progressBar = widgets.IntProgress(
            value=0,
            min=0,
            max=self._widgetsExtraParams['maxTime'].value,
            step=1,
            description='Loading:',
            bar_style='success', # 'success', 'info', 'warning', 'danger' or ''
            orientation='horizontal'
        )
        if not self._silent:
            display(self._progressBar)
    
    def _update_net_params(self):
        # oder of assignment is important (first, update the min and max, later, the value)
        ## @todo: the update of value happens two times (changing min-max and value) and therefore the calculatio are done two times
        if (self._widgetsExtraParams['netType'].value == NetworkType.FULLY_CONNECTED):
            self._widgetsExtraParams['netParam'].min = 0
            self._widgetsExtraParams['netParam'].max = 1
            self._widgetsExtraParams['netParam'].step = 1
            self._widgetsExtraParams['netParam'].value = 0
            self._widgetsExtraParams['netParam'].disabled = True
            self._widgetsExtraParams['netParam'].description = "None"
        elif (self._widgetsExtraParams['netType'].value == NetworkType.ERSOS_RENYI):
            self._widgetsExtraParams['netParam'].disabled = False
            self._widgetsExtraParams['netParam'].min = 0.1
            self._widgetsExtraParams['netParam'].max = 1
            self._widgetsExtraParams['netParam'].step = 0.1
            self._widgetsExtraParams['netParam'].value = 0.5
            self._widgetsExtraParams['netParam'].description = "Network connectivity parameter (link probability)"
        elif (self._widgetsExtraParams['netType'].value == NetworkType.BARABASI_ALBERT):
            self._widgetsExtraParams['netParam'].disabled = False
            maxVal = sum(self._view._initialState.values())-1
            self._widgetsExtraParams['netParam'].min = 1
            self._widgetsExtraParams['netParam'].max = maxVal
            self._widgetsExtraParams['netParam'].step = 1
            self._widgetsExtraParams['netParam'].value = min(maxVal, 3)
            self._widgetsExtraParams['netParam'].description = "Network connectivity parameter (new edges)"            
        elif (self._widgetsExtraParams['netType'].value == NetworkType.SPACE):
            self._widgetsExtraParams['netParam'].value = -1
        
        if (self._widgetsExtraParams['netType'].value == NetworkType.DYNAMIC):
            self._widgetsExtraParams['netParam'].disabled = False
            self._widgetsExtraParams['netParam'].min = 0.0
            self._widgetsExtraParams['netParam'].max = 1
            self._widgetsExtraParams['netParam'].step = 0.05
            self._widgetsExtraParams['netParam'].value = 0.1
            self._widgetsExtraParams['netParam'].description = "Interaction range"
            self._widgetsExtraParams['particleSpeed'].disabled = False
            self._widgetsExtraParams['motionCorrelatedness'].disabled = False
            self._widgetsPlotOnly['showTrace'].disabled = False
            self._widgetsPlotOnly['showInteractions'].disabled = False
        else:
            self._widgetsExtraParams['particleSpeed'].disabled = True
            self._widgetsExtraParams['motionCorrelatedness'].disabled = True
            self._widgetsPlotOnly['showTrace'].disabled = True
            self._widgetsPlotOnly['showInteractions'].disabled = True
    
    def downloadTimeEvolution(self):
        return self._downloadFile(self._view._latestResults[0])
    



## class describing a view on a model
class MuMoTview:
    ## Model view is on
    _mumotModel = None
    ## Figure/axis object to plot view to
    _figure = None
    ## Unique figure number
    _figureNum = None
    ## 3d axes? (False => 2d)
    _axes3d = None
    ## Controller that controls this view @todo - could become None
    _controller = None
    ## Summary logs of view behaviour
    _logs = None
    ## parameter names when used without controller
    _paramNames = None
    ## parameter values when used without controller
    _paramValues = None
    ## silent flag (TRUE = do not try to acquire figure handle from pyplot)
    _silent = None
    ## plot limits (for non-constant system size) @todo: not used?
    _plotLimits = None
    ## command name that generates this view
    _generatingCommand = None
    ## generating keyword arguments
    _generatingKwargs = None
    
    def __init__(self, model, controller, figure = None, params = None, **kwargs):
        self._silent = kwargs.get('silent', False)
        self._mumotModel = model
        self._controller = controller
        self._logs = []
        self._axes3d = False

        self._plotLimits = 1
        #self._plotLimits = 6 ## @todo: why this magic number?
        self._generatingKwargs = kwargs
        if params != None:
            self._paramNames= []
            paramNames, self._paramValues = zip(*params)
            for name in paramNames:
                self._paramNames.append(name.replace('\\','')) ## @todo: have to rationalise how LaTeX characters are handled
        
        if not(self._silent):
            _buildFig(self, figure)
    

    def _resetErrorMessage(self):
        if self._controller != None:
            if not (self._silent):
                self._controller._errorMessage.value= ''

    def _showErrorMessage(self, message):
        if self._controller != None:
            self._controller._errorMessage.value = self._controller._errorMessage.value + message
        else:
            print(message)
            
            
    def _setLog(self, log):
        self._logs = log

    def _log(self, analysis):
        print("Starting", analysis, "with parameters ", end='')
        if self._controller != None:
            paramNames = []
            paramValues = []
            ## @todo: if the afphabetic order is not good, the view could store the desired order in (paramNames) when the controller is constructed
            for name in sorted(self._controller._widgetsFreeParams.keys()):
                paramNames.append(name)
                paramValues.append(self._controller._widgetsFreeParams[name].value)
            for name in sorted(self._controller._widgetsExtraParams.keys()):
                paramNames.append(name)
                paramValues.append(self._controller._widgetsExtraParams[name].value)
        else:
            paramNames = self._paramNames
            paramValues = self._paramValues
            ## @todo: in soloView, this does not show the extra parameters (we should make clearer what the use of showLogs) 

        for i in zip(paramNames, paramValues):
            print('(' + i[0] + '=' + repr(i[1]) + '), ', end='')
        print("at", datetime.datetime.now())
        
                        
    def showLogs(self, tail = False):
        if tail:
            tailLength = 5
            print("Showing last " + str(min(tailLength, len(self._logs))) + " of " + str(len(self._logs)) + " log entries:")
            for log in reversed(self._logs):
                log.show()
                tailLength -= 1
                if tailLength == 0:
                    break
        else:
            for log in self._logs:
                log.show()
            
    def _multirun(self, iterations, randomSeeds):
        colors = cm.rainbow(np.linspace(0, 1, len( self._mumotModel._reactants ) ))  # @UndefinedVariable
        colorMap = {}
        i = 0
        for state in sorted(self._mumotModel._reactants, key=str):
            colorMap[state] = colors[i] 
            i += 1
        
        allEvos = []
        for i in range(iterations):
    #         print("Iteration n." + str(i+1) )
            self._controller._progressBar_multi.value = i
            self._controller._progressBar_multi.description = "Loading " + str(round(i/iterations*100)) + "%:"
            
            logs = self._singleRun(randomSeeds[i])
            if not logs: return # multirun is not supported for this controller
            allEvos.append(logs[1])
            
        ## Plot
        global figureCounter
        plt.figure(figureCounter)
        plt.clf()
        figureCounter += 1
        if (self._visualisationType == "evo"):
#             if not hasattr(self._controller, '_initialState'):
#                 print("ERROR! in multirun arguments. The specified controller does not have the attribute _initialState which is required for visualisationType 'evo'.")
#                 return
            systemSize = sum(self._controller._view._initialState.values())
            maxTime = self._controller._widgetsExtraParams['maxTime'].value
            plt.axis([0, maxTime, 0, systemSize])
            
            for evo in allEvos:
                for state,pop in evo.items():
                    if (state == 'time'): continue
                    plt.plot(evo['time'], pop, color=colorMap[state]) #label=state,
                    
        markers = [plt.Line2D([0,0],[0,0],color=color, marker='', linestyle='-') for color in colorMap.values()]
        plt.legend(markers, colorMap.keys(), bbox_to_anchor=(0.85, 0.95), loc=2, borderaxespad=0.)
        
        return allEvos
    
    ## overwrite this method for views that allow the 'multirun' command
    def _singleRun(self, randomSeed):
        print("ERROR! The command multirun is not supported for this view.")
        return None

## multi-view view (tied closely to MuMoTmultiController)
class MuMoTmultiView(MuMoTview):
    ## view list
    _views = None
    ## axes are used for subplots ('shareAxes = True')
    _axes = None
    ## number of subplots
    _subPlotNum = None
    ## subplot rows
    _numRows = None
    ## subplot columns
    _numColumns = None
    ## use common axes for all plots (False = use subplots)
    _shareAxes = None

    def __init__(self, controller, views, subPlotNum, **kwargs):
        super().__init__(None, controller, **kwargs)
        self._generatingCommand = "mmt.multiView"
        self._views = views
        self._subPlotNum = subPlotNum
        for view in self._views:
            view._figure = self._figure
            view._figureNum = self._figureNum
            view._setLog(self._logs)
            view._controller = controller
        self._shareAxes = kwargs.get('shareAxes', False)        
        if not(self._shareAxes):
            self._numColumns = MULTIPLOT_COLUMNS
            self._numRows = math.ceil(self._subPlotNum / self._numColumns)
        
    def _plot(self):
        plt.figure(self._figureNum)
        plt.clf()
        if self._shareAxes:
            # hold should already be on
            for func, subPlotNum, axes3d in self._controller._replotFunctions:
                func()
        else:
#            subplotNum = 1
            for func, subPlotNum, axes3d in self._controller._replotFunctions:
                if axes3d:
#                    self._figure.add_subplot(self._numRows, self._numColumns, subPlotNum, projection = '3d')
                    plt.subplot(self._numRows, self._numColumns, subPlotNum, projection = '3d')
                else:
                    plt.subplot(self._numRows, self._numColumns, subPlotNum)
                func()
#                subplotNum += 1


    def _setLog(self, log):
        for view in self._views:
            view._setLog(log)


## multi-view controller
class MuMoTmultiController(MuMoTcontroller):
    ## replot function list to invoke on views
    _replotFunctions = None

    def __init__(self, controllers, **kwargs):
        global figureCounter

        self._silent = kwargs.get('silent', False)
        self._replotFunctions = []
        paramNames = []
        paramValues = []
        paramValueDict = {}
        paramLabelDict = {}
        #widgetsExtraParamsTmp = {} # cannot be the final dict already, because it will be erased when constructor is called
        views = []
        subPlotNum = 1
        for controller in controllers:
            for name, value in controller._widgetsFreeParams.items():
                paramValueDict[name] = (value.value, value.min, value.max, value.step)
            paramLabelDict.update(controller._paramLabelDict)
#             for name, value in controller._widgetsExtraParams.items():
#                 widgetsExtraParamsTmp[name] = value
            if controller._replotFunction == None: ## presume this controller is a multi controller (@todo check?)
                for view in controller._view._views:
                    views.append(view)         
                               
#                if view._controller._replotFunction == None: ## presume this controller is a multi controller (@todo check?)
                for func, foo, axes3d in controller._replotFunctions:
                    self._replotFunctions.append((func, subPlotNum, axes3d))                    
#                else:
#                    self._replotFunctions.append((view._controller._replotFunction, subPlotNum, view._axes3d))                    
            else:
                views.append(controller._view)
#                 if controller._replotFunction == None: ## presume this controller is a multi controller (@todo check?)
#                     for func, foo in controller._replotFunctions:
#                         self._replotFunctions.append((func, subPlotNum))                    
#                 else:
                self._replotFunctions.append((controller._replotFunction, subPlotNum, controller._view._axes3d))                    
            subPlotNum += 1

        for name, value in paramValueDict.items():
            paramNames.append(name)
            paramValues.append(value)
            
#         for view in self._views:
#             if view._controller._replotFunction == None: ## presume this controller is a multi controller (@todo check?)
#                 for func in view._controller._replotFunctions:
#                     self._replotFunctions.append(func)                    
#             else:
#                 self._replotFunctions.append(view._controller._replotFunction)
#             view._controller = self
        
        super().__init__(paramValues, paramNames, paramLabelDict, False, **kwargs)
        
        addProgressBar = False
        for controller in controllers:
            for name, widget in controller._widgetsExtraParams.items():
                self._widgetsExtraParams[name] = widget
            for name, widget in controller._widgetsPlotOnly.items():
                self._widgetsPlotOnly[name] = widget
            if controller._progressBar:
                addProgressBar = True
        if self._widgetsExtraParams or self._widgetsPlotOnly:
            if not self._silent:
                advancedWidgets = []
                for widget in self._widgetsExtraParams.values():
                    advancedWidgets.append(widget)
                for widget in self._widgetsPlotOnly.values():
                    advancedWidgets.append(widget)
                advancedPage = widgets.Box(children=advancedWidgets)
                advancedOpts = widgets.Accordion(children=[advancedPage])
                advancedOpts.set_title(0, 'Advanced options')
                display(advancedOpts)
        if addProgressBar:
            # Loading bar (useful to give user progress status for long executions)
            self._progressBar = widgets.IntProgress(
                value=0,
                min=0,
                max=self._widgetsExtraParams['maxTime'].value,
                #step=1,
                description='Loading:',
                bar_style='success', # 'success', 'info', 'warning', 'danger' or ''
                orientation='horizontal'
            )
            if not self._silent:
                display(self._progressBar)

        self._view = MuMoTmultiView(self, views, subPlotNum - 1, **kwargs)
                
        for controller in controllers:
            controller._setErrorWidget(self._errorMessage)
        
        ## @todo handle correctly the re-draw only widgets and function
        self._setReplotFunction( self._view._plot, self._view._plot)

        #silent = kwargs.get('silent', False)
        if not self._silent:
            self._view._plot()

## time evolution view on model including state variables and noise (specialised by MuMoTtimeEvoStateVarView and MuMoTtimeEvoNoiseView)
class MuMoTtimeEvolutionView(MuMoTview):
    ## 1st state variable
    _stateVariable1 = None
    ## 2nd state variable 
    _stateVariable2 = None
    ## 3rd state variable 
    _stateVariable3 = None
    ## 4th state variable 
    _stateVariable4 = None
    ## end time of numerical simulation
    _tend = None
    ## time step of numerical simulation
    _tstep = None
    
  
    def __init__(self, model, controller, stateVariable1, stateVariable2, stateVariable3 = None, stateVariable4 = None, tend = 100, tstep = 0.01, figure = None, params = None, **kwargs):
        #if model._systemSize == None and model._constantSystemSize == True:
        #    print("Cannot construct time evolution -based plot until system size is set, using substitute()")
        #    return
        silent = kwargs.get('silent', False)
        super().__init__(model, controller, figure, params, **kwargs)
        
        if 'fontsize' in kwargs:
            self._chooseFontSize = kwargs['fontsize']
        else:
            self._chooseFontSize=None
        self._xlab = kwargs.get('xlab', r'time t')
        self._ylab = kwargs.get('ylab', r'evolution of states')
        
        self._legend_loc = kwargs.get('legend_loc', 'upper left')
        
        self._stateVariable1 = process_sympy(stateVariable1)
        self._stateVariable2 = process_sympy(stateVariable2)
        if stateVariable3 != None:
            self._stateVariable3 = process_sympy(stateVariable3)
        if stateVariable4 != None:
            self._stateVariable4 = process_sympy(stateVariable4)
            
        self._tend = tend
        self._tstep = tstep
        
        if not(silent):
            self._plot_NumSolODE()

    
    ## gets and returns names and values from widgets
    def _get_argDict(self):
        plotLimits = 1
        if self._controller != None:
            paramNames = []
            paramValues = []
            for name, value in self._controller._widgetsFreeParams.items():
                # throw away formatting for constant reactants
                #name = name.replace('(','')
                #name = name.replace(')','')
                
                paramNames.append(name)
                paramValues.append(value.value)
            if self._controller._plotLimitsWidget != None:
                plotLimits = self._controller._plotLimitsWidget.value
        else:
            paramNames = self._paramNames
            paramValues = self._paramValues   
                 
        #funcs = self._mumotModel._getFuncs()
        argNamesSymb = list(map(Symbol, paramNames))
        argDict = dict(zip(argNamesSymb, paramValues))
        for key in argDict:
            if key in self._mumotModel._constantReactants:
                argDict[Symbol('Phi_'+str(key))] = argDict.pop(key)
        if self._controller._systemSizeWidget != None:
            systemSize = Symbol('systemSize')
            argDict[systemSize] = self._controller._systemSizeWidget.value
        
        return argDict
    
    
    def _getInitCondsFromSlider(self):
        if self._controller != None:
            paramNames = []
            paramValues = []
            for reactant in self._mumotModel._reactants:
                if reactant not in self._mumotModel._constantReactants:
                    for name, value in self._controller._widgetsFreeParams.items():
                        if name == latex(Symbol('Phi^0_'+str(reactant))):
                            paramNames.append(name)
                            paramValues.append(value.value)
                
        argNamesSymb = list(map(Symbol, paramNames))
        argDict = dict(zip(argNamesSymb, paramValues))
        
        return argDict
    
    ## calculates right-hand side of ODE system
    def _get_eqsODE(self, y_old, time):
        SVsub = {}
        SVsub[self._stateVariable1] = y_old[0]
        SVsub[self._stateVariable2] = y_old[1]
        if self._stateVariable3:
            SVsub[self._stateVariable3] = y_old[2]
        if self._stateVariable4:
            SVsub[self._stateVariable4] = y_old[3]
        plotLimits = 1
        if self._controller != None:
            paramNames = []
            paramValues = []
            for name, value in self._controller._widgetsFreeParams.items():
                # throw away formatting for constant reactants
#                 name = name.replace('(','')
#                 name = name.replace(')','')
                paramNames.append(name)
                paramValues.append(value.value)
            if self._controller._plotLimitsWidget != None:
                plotLimits = self._controller._plotLimitsWidget.value
        else:
            paramNames = self._paramNames
            paramValues = self._paramValues            
        funcs = self._mumotModel._getFuncs()
        argNamesSymb = list(map(Symbol, paramNames))
        argDict = dict(zip(argNamesSymb, paramValues))
        argDict[self._mumotModel._systemSize] = 1
        
        EQ1 = self._mumotModel._equations[self._stateVariable1].subs(argDict)
        EQ1 = EQ1.subs(SVsub)
        EQ2 = self._mumotModel._equations[self._stateVariable2].subs(argDict)
        EQ2 = EQ2.subs(SVsub)
        ode_sys = [EQ1, EQ2]
        if self._stateVariable3:
            EQ3 = self._mumotModel._equations[self._stateVariable3].subs(argDict)
            EQ3 = EQ3.subs(SVsub)
            ode_sys.append(EQ3)
        if self._stateVariable4:
            EQ4 = self._mumotModel._equations[self._stateVariable4].subs(argDict)
            EQ4 = EQ4.subs(SVsub)
            ode_sys.append(EQ4)
            
        return ode_sys
    
    
            
    ## calculates stationary states of 2d system
    def _get_fixedPoints2d(self):
        plotLimits = 1
        if self._controller != None:
            paramNames = []
            paramValues = []
            for name, value in self._controller._widgetsFreeParams.items():
                # throw away formatting for constant reactants
#                 name = name.replace('(','')
#                 name = name.replace(')','')
                paramNames.append(name)
                paramValues.append(value.value)
            if self._controller._plotLimitsWidget != None:
                plotLimits = self._controller._plotLimitsWidget.value
        else:
            paramNames = self._paramNames
            paramValues = self._paramValues            
        funcs = self._mumotModel._getFuncs()
        argNamesSymb = list(map(Symbol, paramNames))
        argDict = dict(zip(argNamesSymb, paramValues))
        argDict[self._mumotModel._systemSize] = 1
        
        EQ1 = self._mumotModel._equations[self._stateVariable1].subs(argDict)
        EQ2 = self._mumotModel._equations[self._stateVariable2].subs(argDict)
        eps=1e-8
        EQsol = solve((EQ1, EQ2), (self._stateVariable1, self._stateVariable2), dict=True)
        realEQsol = [{self._stateVariable1: re(EQsol[kk][self._stateVariable1]), self._stateVariable2: re(EQsol[kk][self._stateVariable2])} for kk in range(len(EQsol)) if (Abs(im(EQsol[kk][self._stateVariable1]))<=eps and Abs(im(EQsol[kk][self._stateVariable2]))<=eps)]
        
        MAT = Matrix([EQ1, EQ2])
        JAC = MAT.jacobian([self._stateVariable1,self._stateVariable2])
        
        eigList = []
        for nn in range(len(realEQsol)): 
            evSet = {}
            JACsub=JAC.subs([(self._stateVariable1, realEQsol[nn][self._stateVariable1]), (self._stateVariable2, realEQsol[nn][self._stateVariable2])])
            #evSet = JACsub.eigenvals()
            eigVects = JACsub.eigenvects()
            for kk in range(len(eigVects)):
                evSet[eigVects[kk][0]] = (eigVects[kk][1], eigVects[kk][2])
            eigList.append(evSet)
        return realEQsol, eigList #returns two lists of dictionaries
    
    ## calculates stationary states of 3d system
    def _get_fixedPoints3d(self):
        plotLimits = 1
        if self._controller != None:
            paramNames = []
            paramValues = []
            for name, value in self._controller._widgetsFreeParams.items():
                # throw away formatting for constant reactants
#                 name = name.replace('(','')
#                 name = name.replace(')','')
                paramNames.append(name)
                paramValues.append(value.value)
            if self._controller._plotLimitsWidget != None:
                plotLimits = self._controller._plotLimitsWidget.value
        else:
            paramNames = self._paramNames
            paramValues = self._paramValues            
        funcs = self._mumotModel._getFuncs()
        argNamesSymb = list(map(Symbol, paramNames))
        argDict = dict(zip(argNamesSymb, paramValues))
        argDict[self._mumotModel._systemSize] = 1
        
        EQ1 = self._mumotModel._equations[self._stateVariable1].subs(argDict)
        EQ2 = self._mumotModel._equations[self._stateVariable2].subs(argDict)
        EQ3 = self._mumotModel._equations[self._stateVariable3].subs(argDict)
        eps=1e-8
        EQsol = solve((EQ1, EQ2, EQ3), (self._stateVariable1, self._stateVariable2, self._stateVariable3), dict=True)
        realEQsol = [{self._stateVariable1: re(EQsol[kk][self._stateVariable1]), self._stateVariable2: re(EQsol[kk][self._stateVariable2]), self._stateVariable3: re(EQsol[kk][self._stateVariable3])} for kk in range(len(EQsol)) if (Abs(im(EQsol[kk][self._stateVariable1]))<=eps and Abs(im(EQsol[kk][self._stateVariable2]))<=eps and Abs(im(EQsol[kk][self._stateVariable3]))<=eps)]
        
        MAT = Matrix([EQ1, EQ2, EQ3])
        JAC = MAT.jacobian([self._stateVariable1,self._stateVariable2,self._stateVariable3])
        
        eigList = []
        for nn in range(len(realEQsol)): 
            evSet = {}
            JACsub=JAC.subs([(self._stateVariable1, realEQsol[nn][self._stateVariable1]), (self._stateVariable2, realEQsol[nn][self._stateVariable2]), (self._stateVariable3, realEQsol[nn][self._stateVariable3])])
            #evSet = JACsub.eigenvals()
            eigVects = JACsub.eigenvects()
            for kk in range(len(eigVects)):
                evSet[eigVects[kk][0]] = (eigVects[kk][1], eigVects[kk][2])
            eigList.append(evSet)
        return realEQsol, eigList #returns two lists of dictionaries
    
    
    def _plot_NumSolODE(self):
        if not(self._silent): ## @todo is this necessary?
            plt.figure(self._figureNum)
            plt.clf()
            self._resetErrorMessage()
        self._showErrorMessage(str(self))
        
    
    def _print_standalone_view_cmd(self):
        with io.capture_output() as log:
            print('Bookmark feature for standalone view not implemented for time-dependent soultion of ODE.')
#             logStr = self._generatingCommand + "(<modelName>, None, '" + str(self._stateVariable1) + "', '" + str(self._stateVariable2) +"', "
#             if self._stateVariable3 != None:
#                 logStr += "'" + str(self._stateVariable3) + "', "
#             logStr += "params = ["
#             for name, value in self._controller._widgetsFreeParams.items():
# #                name = name.replace('\\', '\\\\')
#                 name = name.replace('(', '')
#                 name = name.replace(')', '')
#                 logStr += "('" + name + "', " + str(value.value) + "), "
#             if len(self._controller._widgetsFreeParams.items()) > 0:
#                 logStr = logStr[:-2] # throw away last ", "
#             logStr += "]"
#             if self._generatingKwargs != None:
#                 logStr += ", "
#                 for key in self._generatingKwargs:
#                     logStr += key + " = " + str(self._generatingKwargs[key]) + ", "
#                 if len(self._generatingKwargs) > 0:
#                     logStr = logStr[:-2]  # throw away last ", "
#             logStr += ")"
#             print(logStr)    
        self._logs.append(log)
        

## numerical solution of state variables plot view on model
class MuMoTtimeEvoStateVarView(MuMoTtimeEvolutionView):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._generatingCommand = "mmt.MuMoTtimeEvoStateVarView"

    def _plot_NumSolODE(self):
        super()._plot_NumSolODE()
        
        NrDP = int(self._tend/self._tstep) + 1
        time = np.linspace(0, self._tend, NrDP)
        
        initDict = self._getInitCondsFromSlider()
        assert (2 <= len(initDict) <= 4),"Not implemented: This feature is available only for systems with 2, 3 or 4 time-dependent reactants!"

        
        SV1_0 = initDict[Symbol(latex(Symbol('Phi^0_'+str(self._stateVariable1))))]
        SV2_0 = initDict[Symbol(latex(Symbol('Phi^0_'+str(self._stateVariable2))))]
        y0 = [SV1_0, SV2_0]
        if len(initDict) > 2:
            SV3_0 = initDict[Symbol(latex(Symbol('Phi^0_'+str(self._stateVariable3))))]
            y0.append(SV3_0)
        if len(initDict) > 3:
            SV4_0 = initDict[Symbol(latex(Symbol('Phi^0_'+str(self._stateVariable4))))]
            y0.append(SV4_0)
        
        sol_ODE = odeint(self._get_eqsODE, y0, time)  
          
        x_data = [time for kk in range(len(self._get_eqsODE(y0, time)))]
        y_data = [sol_ODE[:, kk] for kk in range(len(self._get_eqsODE(y0, time)))]
        
        c_labels = [r'$'+latex(Symbol('Phi_'+str(self._stateVariable1)))+'$', r'$'+latex(Symbol('Phi_'+str(self._stateVariable2)))+'$'] 
        if self._stateVariable3:
            c_labels.append(r'$'+latex(Symbol('Phi_'+str(self._stateVariable3)))+'$')
        if self._stateVariable4:
            c_labels.append(r'$'+latex(Symbol('Phi_'+str(self._stateVariable4)))+'$')         
        
        _fig_formatting_2D(xdata=x_data, ydata = y_data , xlab = self._xlab, ylab = self._ylab, 
                           fontsize=self._chooseFontSize, curvelab=c_labels, legend_loc=self._legend_loc, grid = True)
#        plt.set_aspect('equal') ## @todo


        

## field view on model (specialised by MuMoTvectorView and MuMoTstreamView)
class MuMoTfieldView(MuMoTview):
    ## 1st state variable (x-dimension)
    _stateVariable1 = None
    ## 2nd state variable (y-dimension)
    _stateVariable2 = None
    ## 3rd state variable (z-dimension) 
    _stateVariable3 = None
    ## X ordinates array
    _X = None
    ## Y ordinates array
    _Y = None 
    ## Z ordinates array
    _Z = None
    ## X derivatives array 
    _X = None
    ## Y derivatives array
    _Y = None
    ## Z derivatives array
    _Z = None 
    ## speed array
    _speed = None 
    ## class-global dictionary of memoised masks with (mesh size, dimension) as key
    _mask = {} 
    
    def __init__(self, model, controller, stateVariable1, stateVariable2, stateVariable3 = None, figure = None, params = None, **kwargs):
        if model._systemSize == None and model._constantSystemSize == True:
            print("Cannot construct field-based plot until system size is set, using substitute()")
            return
        silent = kwargs.get('silent', False)
        super().__init__(model, controller, figure, params, **kwargs)
        
        if 'fontsize' in kwargs:
            self._chooseFontSize = kwargs['fontsize']
        else:
            self._chooseFontSize=None
        self._showFixedPoints = kwargs.get('showFixedPoints', True)
        self._xlab = kwargs.get('xlab', r'$'+latex(Symbol('Phi_'+str(stateVariable1)))+'$')
        self._ylab = kwargs.get('ylab', r'$'+latex(Symbol('Phi_'+str(stateVariable2)))+'$')
        if stateVariable3:
            self._zlab = kwargs.get('zlab', str(stateVariable3)) 
        
        self._stateVariable1 = process_sympy(stateVariable1)
        self._stateVariable2 = process_sympy(stateVariable2)
        if stateVariable3 != None:
            self._axes3d = True
            self._stateVariable3 = process_sympy(stateVariable3)
        _mask = {}

        if not(silent):
            self._plot_field()

    
    ## gets and returns names and values from widgets
    def _get_argDict(self):
        plotLimits = 1
        if self._controller != None:
            paramNames = []
            paramValues = []
            for name, value in self._controller._widgetsFreeParams.items():
                # throw away formatting for constant reactants
                #name = name.replace('(','')
                #name = name.replace(')','')
                
                paramNames.append(name)
                paramValues.append(value.value)
            if self._controller._plotLimitsWidget != None:
                plotLimits = self._controller._plotLimitsWidget.value
        else:
            paramNames = self._paramNames
            paramValues = self._paramValues   
                 
        #funcs = self._mumotModel._getFuncs()
        argNamesSymb = list(map(Symbol, paramNames))
        argDict = dict(zip(argNamesSymb, paramValues))
        for key in argDict:
            if key in self._mumotModel._constantReactants:
                argDict[Symbol('Phi_'+str(key))] = argDict.pop(key)
        if self._controller._systemSizeWidget != None:
            systemSize = Symbol('systemSize')
            argDict[systemSize] = self._controller._systemSizeWidget.value
        
        return argDict
    


#    def __init__(self, model, controller, stateVariable1, stateVariable2, stateVariable3 = None, figure = None, params = None, **kwargs):

    def _print_standalone_view_cmd(self):
        with io.capture_output() as log:
            if self._generatingCommand == 'mmt.MuMoTnoiseView':
                print('Bookmark functionality not implemented for MuMoTnoiseView')
                #logStr = self._generatingCommand + "(<modelName>, None, '" + str(self._SOL_2ndOrdMomDict) + "', '" + str(self._stateVariable1) + "', '" + str(self._stateVariable2) + "', "
            else:
                logStr = self._generatingCommand + "(<modelName>, None, '" + str(self._stateVariable1) + "', '" + str(self._stateVariable2) +"', "
                if self._stateVariable3 != None:
                    logStr += "'" + str(self._stateVariable3) + "', "
                logStr += "params = ["
                for name, value in self._controller._widgetsFreeParams.items():
    #                name = name.replace('\\', '\\\\')
                    name = name.replace('(', '')
                    name = name.replace(')', '')
                    logStr += "('" + name + "', " + str(value.value) + "), "
                if len(self._controller._widgetsFreeParams.items()) > 0:
                    logStr = logStr[:-2] # throw away last ", "
                logStr += "]"
                if self._generatingKwargs != None:
                    logStr += ", "
                    for key in self._generatingKwargs:
                        logStr += key + " = " + str(self._generatingKwargs[key]) + ", "
                    if len(self._generatingKwargs) > 0:
                        logStr = logStr[:-2]  # throw away last ", "
                logStr += ")"
                print(logStr)    
            self._logs.append(log)

            
    ## calculates stationary states of 2d system
    def _get_fixedPoints2d(self):
        plotLimits = 1
        if self._controller != None:
            paramNames = []
            paramValues = []
            for name, value in self._controller._widgetsFreeParams.items():
                # throw away formatting for constant reactants
#                 name = name.replace('(','')
#                 name = name.replace(')','')
                paramNames.append(name)
                paramValues.append(value.value)
            if self._controller._plotLimitsWidget != None:
                plotLimits = self._controller._plotLimitsWidget.value
        else:
            paramNames = self._paramNames
            paramValues = self._paramValues            
        funcs = self._mumotModel._getFuncs()
        argNamesSymb = list(map(Symbol, paramNames))
        argDict = dict(zip(argNamesSymb, paramValues))
        argDict[self._mumotModel._systemSize] = 1
       
#         if self._controller != None:
#             paramNames = []
#             paramValues = []
#             for name, value in self._controller._widgetsFreeParams.items():
#                 paramNames.append(name)
#                 paramValues.append(value.value)          
#         else:
#             paramNames = self._paramNames
#             paramValues = self._paramValues           
#             
#         argNamesSymb = list(map(Symbol, paramNames))
#         argDict = dict(zip(argNamesSymb, paramValues))
#         argDict[self._mumotModel._systemSize] = 1
        
        EQ1 = self._mumotModel._equations[self._stateVariable1].subs(argDict)
        EQ2 = self._mumotModel._equations[self._stateVariable2].subs(argDict)
        eps=1e-8
        EQsol = solve((EQ1, EQ2), (self._stateVariable1, self._stateVariable2), dict=True)
        #for kk in range(len(EQsol)):
        #    print(EQsol[kk])
        realEQsol = [{self._stateVariable1: re(EQsol[kk][self._stateVariable1]), self._stateVariable2: re(EQsol[kk][self._stateVariable2])} for kk in range(len(EQsol)) if (Abs(im(EQsol[kk][self._stateVariable1]))<=eps and Abs(im(EQsol[kk][self._stateVariable2]))<=eps)]
        
        MAT = Matrix([EQ1, EQ2])
        JAC = MAT.jacobian([self._stateVariable1,self._stateVariable2])
        
        eigList = []
        #for nn in range(len(realEQsol)): 
        #    JACsub=JAC.subs([(self._stateVariable1, realEQsol[nn][self._stateVariable1]), (self._stateVariable2, realEQsol[nn][self._stateVariable2])])
        #    evSet = JACsub.eigenvals()
        #    eigList.append(evSet)
        for nn in range(len(realEQsol)): 
            evSet = {}
            JACsub=JAC.subs([(self._stateVariable1, realEQsol[nn][self._stateVariable1]), (self._stateVariable2, realEQsol[nn][self._stateVariable2])])
            #evSet = JACsub.eigenvals()
            eigVects = JACsub.eigenvects()
            for kk in range(len(eigVects)):
                evSet[eigVects[kk][0]] = (eigVects[kk][1], eigVects[kk][2])
            eigList.append(evSet)
        return realEQsol, eigList #returns two lists of dictionaries
    
    ## calculates stationary states of 3d system
    def _get_fixedPoints3d(self):
        plotLimits = 1
        if self._controller != None:
            paramNames = []
            paramValues = []
            for name, value in self._controller._widgetsFreeParams.items():
                # throw away formatting for constant reactants
#                 name = name.replace('(','')
#                 name = name.replace(')','')
                paramNames.append(name)
                paramValues.append(value.value)
            if self._controller._plotLimitsWidget != None:
                plotLimits = self._controller._plotLimitsWidget.value
        else:
            paramNames = self._paramNames
            paramValues = self._paramValues            
        funcs = self._mumotModel._getFuncs()
        argNamesSymb = list(map(Symbol, paramNames))
        argDict = dict(zip(argNamesSymb, paramValues))
        argDict[self._mumotModel._systemSize] = 1
        
#         if self._controller != None:
#             paramNames = []
#             paramValues = []
#             for name, value in self._controller._widgetsFreeParams.items():
#                 paramNames.append(name)
#                 paramValues.append(value.value)          
#         else:
#             paramNames = self._paramNames
#             paramValues = self._paramValues           
#             
#         argNamesSymb = list(map(Symbol, paramNames))
#         argDict = dict(zip(argNamesSymb, paramValues))
#         argDict[self._mumotModel._systemSize] = 1
        
        EQ1 = self._mumotModel._equations[self._stateVariable1].subs(argDict)
        EQ2 = self._mumotModel._equations[self._stateVariable2].subs(argDict)
        EQ3 = self._mumotModel._equations[self._stateVariable3].subs(argDict)
        eps=1e-8
        EQsol = solve((EQ1, EQ2, EQ3), (self._stateVariable1, self._stateVariable2, self._stateVariable3), dict=True)
        realEQsol = [{self._stateVariable1: re(EQsol[kk][self._stateVariable1]), self._stateVariable2: re(EQsol[kk][self._stateVariable2]), self._stateVariable3: re(EQsol[kk][self._stateVariable3])} for kk in range(len(EQsol)) if (Abs(im(EQsol[kk][self._stateVariable1]))<=eps and Abs(im(EQsol[kk][self._stateVariable2]))<=eps and Abs(im(EQsol[kk][self._stateVariable3]))<=eps)]
        
        MAT = Matrix([EQ1, EQ2, EQ3])
        JAC = MAT.jacobian([self._stateVariable1,self._stateVariable2,self._stateVariable3])
        
        eigList = []
        #for nn in range(len(realEQsol)): 
        #    JACsub=JAC.subs([(self._stateVariable1, realEQsol[nn][self._stateVariable1]), (self._stateVariable2, realEQsol[nn][self._stateVariable2]), (self._stateVariable3, realEQsol[nn][self._stateVariable3])])
        #    evSet = JACsub.eigenvals()
        #    eigList.append(evSet)
        for nn in range(len(realEQsol)): 
            evSet = {}
            JACsub=JAC.subs([(self._stateVariable1, realEQsol[nn][self._stateVariable1]), (self._stateVariable2, realEQsol[nn][self._stateVariable2]), (self._stateVariable3, realEQsol[nn][self._stateVariable3])])
            #evSet = JACsub.eigenvals()
            eigVects = JACsub.eigenvects()
            for kk in range(len(eigVects)):
                evSet[eigVects[kk][0]] = (eigVects[kk][1], eigVects[kk][2])
            eigList.append(evSet)
        return realEQsol, eigList #returns two lists of dictionaries
    
    
    def _plot_field(self):
        if not(self._silent): ## @todo is this necessary?
            plt.figure(self._figureNum)
            plt.clf()
            self._resetErrorMessage()
        self._showErrorMessage(str(self))

    ## helper for _get_field_2d() and _get_field_3d()
    def _get_field(self):
        plotLimits = 1
        if self._controller != None:
            paramNames = []
            paramValues = []
            for name, value in self._controller._widgetsFreeParams.items():
                # throw away formatting for constant reactants
#                 name = name.replace('(','')
#                 name = name.replace(')','')
                paramNames.append(name)
                paramValues.append(value.value)
            if self._controller._plotLimitsWidget != None:
                plotLimits = self._controller._plotLimitsWidget.value
        else:
            paramNames = self._paramNames
            paramValues = self._paramValues           
        funcs = self._mumotModel._getFuncs()
        argNamesSymb = list(map(Symbol, paramNames))
        argDict = dict(zip(argNamesSymb, paramValues))
        
        
        return (funcs, argNamesSymb, argDict, paramNames, paramValues, plotLimits)

    ## get 2-dimensional field for plotting
    def _get_field2d(self, kind, meshPoints, plotLimits = 1):
        with io.capture_output() as log:
            self._log(kind)
            (funcs, argNamesSymb, argDict, paramNames, paramValues, plotLimits) = self._get_field()
            self._Y, self._X = np.mgrid[0:plotLimits:complex(0, meshPoints), 0:plotLimits:complex(0, meshPoints)]
            if self._mumotModel._constantSystemSize:
                mask = self._mask.get((meshPoints, 2))
                if mask is None:
                    mask = np.zeros(self._X.shape, dtype=bool)
                    upperright = np.triu_indices(meshPoints) ## @todo: allow user to set mesh points with keyword 
                    mask[upperright] = True
                    np.fill_diagonal(mask, False)
                    mask = np.flipud(mask)
                    self._mask[(meshPoints, 2)] = mask
            self._Xdot = funcs[self._stateVariable1](*self._mumotModel._getArgTuple2d(paramNames, paramValues, argDict, self._stateVariable1, self._stateVariable2, self._X, self._Y))
            self._Ydot = funcs[self._stateVariable2](*self._mumotModel._getArgTuple2d(paramNames, paramValues, argDict, self._stateVariable1, self._stateVariable2, self._X, self._Y))
            try:
                self._speed = np.log(np.sqrt(self._Xdot ** 2 + self._Ydot ** 2))
            except:
#                self._speed = np.ones(self._X.shape, dtype=float)
                self._speed = None
            if self._mumotModel._constantSystemSize:
                self._Xdot = np.ma.array(self._Xdot, mask=mask)
                self._Ydot = np.ma.array(self._Ydot, mask=mask)        
        self._logs.append(log)

    ## get 3-dimensional field for plotting        
    def _get_field3d(self, kind, meshPoints, plotLimits = 1):
        with io.capture_output() as log:
            self._log(kind)
            (funcs, argNamesSymb, argDict, paramNames, paramValues, plotLimits) = self._get_field()
            self._Z, self._Y, self._X = np.mgrid[0:plotLimits:complex(0, meshPoints), 0:plotLimits:complex(0, meshPoints), 0:plotLimits:complex(0, meshPoints)]
            if self._mumotModel._constantSystemSize:
                mask = self._mask.get((meshPoints, 3))
                if mask is None:
    #                mask = np.zeros(self._X.shape, dtype=bool)
    #                 upperright = np.triu_indices(meshPoints) ## @todo: allow user to set mesh points with keyword 
    #                 mask[upperright] = True
    #                 np.fill_diagonal(mask, False)
    #                 mask = np.flipud(mask)
                    mask = self._X + self._Y + self._Z >= 1
    #                mask = mask.astype(int)
                    self._mask[(meshPoints, 3)] = mask
            self._Xdot = funcs[self._stateVariable1](*self._mumotModel._getArgTuple3d(paramNames, paramValues, argDict, self._stateVariable1, self._stateVariable2, self._stateVariable3, self._X, self._Y, self._Z))
            self._Ydot = funcs[self._stateVariable2](*self._mumotModel._getArgTuple3d(paramNames, paramValues, argDict, self._stateVariable1, self._stateVariable2, self._stateVariable3, self._X, self._Y, self._Z))
            self._Zdot = funcs[self._stateVariable3](*self._mumotModel._getArgTuple3d(paramNames, paramValues, argDict, self._stateVariable1, self._stateVariable2, self._stateVariable3, self._X, self._Y, self._Z))
            try:
                self._speed = np.log(np.sqrt(self._Xdot ** 2 + self._Ydot ** 2 + self._Zdot ** 2))
            except:
                self._speed = None
#            self._Xdot = self._Xdot * mask
#            self._Ydot = self._Ydot * mask
#            self._Zdot = self._Zdot * mask
            if self._mumotModel._constantSystemSize:
                self._Xdot = np.ma.array(self._Xdot, mask=mask)
                self._Ydot = np.ma.array(self._Ydot, mask=mask)        
                self._Zdot = np.ma.array(self._Zdot, mask=mask)
        self._logs.append(log)


## stream plot with noise ellipses view on model
class MuMoTnoiseView(MuMoTfieldView):
    ## solution 1st order moments (noise in vKE)
    _SOL_1stOrderMomDict = None
    ## replacement dictionary for symbols of 1st order moments
    _NoiseSubs1stOrder = None
    ## solution 2nd order moments (noise in vKE)
    _SOL_2ndOrdMomDict = None
    ## replacement dictionary for symbols of 2nd order moments
    _NoiseSubs2ndOrder = None
    ## set for checking number of time-dependent reactants
    _checkReactants = None
    ## set for checking constant reactants
    _checkConstReactants = None
    
    _noiseStatSol = None
 
    def __init__(self, model, controller, SOL_2ndOrd, stateVariable1, stateVariable2, stateVariable3=None, figure = None, params = None, **kwargs):
        if model._systemSize == None and model._constantSystemSize == True:
            print("Cannot construct field-based plot until system size is set, using substitute()")
            return
        #self._noiseStatSol = noiseStatSol
        #self._SOL_1stOrderMomDict, self._NoiseSubs1stOrder, self._SOL_2ndOrdMomDict, self._NoiseSubs2ndOrder = self._noiseStatSol
        self._SOL_2ndOrdMomDict = SOL_2ndOrd
        self._checkReactants = model._reactants
        if model._constantReactants:
            self._checkConstReactants = model._constantReactants
        silent = kwargs.get('silent', False)
        super().__init__(model, controller, stateVariable1, stateVariable2, stateVariable3, figure, params, **kwargs) 
        self._generatingCommand = "mmt.MuMoTnoiseView"
        
    def _plot_field(self):
        super()._plot_field()
        
        Phi_stateVar1 = Symbol('Phi_'+str(self._stateVariable1)) 
        Phi_stateVar2 = Symbol('Phi_'+str(self._stateVariable2))
        eta_stateVar1 = Symbol('eta_'+str(self._stateVariable1)) 
        eta_stateVar2 = Symbol('eta_'+str(self._stateVariable2))
        M_2 = Symbol('M_2')
        
        eta_cross = eta_stateVar1*eta_stateVar2
        for key in self._SOL_2ndOrdMomDict:
            if key == self._SOL_2ndOrdMomDict[key] or key in self._SOL_2ndOrdMomDict[key].args:
                for key2 in self._SOL_2ndOrdMomDict:
                    if key2 != key and key2 != M_2(eta_cross):
                        self._SOL_2ndOrdMomDict[key] = self._SOL_2ndOrdMomDict[key].subs(key, self._SOL_2ndOrdMomDict[key2])
                   
        checkReactants = copy.deepcopy(self._checkReactants)
        if self._checkConstReactants:
            checkConstReactants = copy.deepcopy(self._checkConstReactants)
            for reactant in checkReactants:
                if reactant in checkConstReactants:
                    checkReactants.remove(reactant)
        assert (len(checkReactants) == 2),"Not implemented: This feature is available only for systems with exactly 2 time-dependent reactants!"
        realEQsol, eigList = self._get_fixedPoints2d()
        systemSize = Symbol('systemSize')
        argDict = self._get_argDict()
        
        PhiSubList = []
        for kk in range(len(realEQsol)):
            PhiSubDict={}
            for solXi in realEQsol[kk]:
                PhiSubDict[Symbol('Phi_'+str(solXi))] = realEQsol[kk][solXi]
            PhiSubList.append(PhiSubDict)
        
        SOL_2ndOrdMomDictList = []
        for nn in range(len(PhiSubList)):
            SOL_2ndOrdMomDict = copy.deepcopy(self._SOL_2ndOrdMomDict)
            for sol in SOL_2ndOrdMomDict:
                SOL_2ndOrdMomDict[sol] = SOL_2ndOrdMomDict[sol].subs(PhiSubList[nn])
                SOL_2ndOrdMomDict[sol] = SOL_2ndOrdMomDict[sol].subs(argDict)
            SOL_2ndOrdMomDictList.append(SOL_2ndOrdMomDict)
            
        Evects = []
        EvectsPlot = []
        EV = []
        EVplot = []
        for kk in range(len(eigList)):
            EVsub = []
            EvectsSub = []
            for key in eigList[kk]:
                for jj in range(len(eigList[kk][key][1])):
                    EvectsSub.append(eigList[kk][key][1][jj].evalf())
                if eigList[kk][key][0] >1:
                    for jj in range(eigList[kk][key][0]):
                        EVsub.append(key.evalf())
                else:
                    EVsub.append(key.evalf())
                    
            EV.append(EVsub)
            Evects.append(EvectsSub)
            if self._mumotModel._constantSystemSize == True:
                if (0 <= re(realEQsol[kk][self._stateVariable1]) <= 1 and 0 <= re(realEQsol[kk][self._stateVariable2]) <= 1):
                    EVplot.append(EVsub)
                    EvectsPlot.append(EvectsSub)
            else:
                EVplot.append(EVsub)
                EvectsPlot.append(EvectsSub)

        angle_ell_list = []
        projection_angle_list = []
        vec1 = Matrix([ [0], [1] ])
        for nn in range(len(EvectsPlot)):
            vec2 = EvectsPlot[nn][0]
            vec2norm = vec2.norm()
            vec2 = vec2/vec2norm
            vec3 = EvectsPlot[nn][0]
            vec3norm = vec3.norm()
            vec3 = vec3/vec3norm
            if vec2norm >= vec3norm:
                angle_ell = acos(vec1.dot(vec2)/(vec1.norm()*vec2.norm())).evalf()
            else:
                angle_ell = acos(vec1.dot(vec3)/(vec1.norm()*vec3.norm())).evalf()
            angle_ell = angle_ell.evalf()
            projection_angle_list.append(angle_ell)
            angle_ell_deg = 180*angle_ell/pi.evalf()
            angle_ell_list.append(round(angle_ell_deg,5))
        projection_angle_list = [abs(projection_angle_list[kk]) if abs(projection_angle_list[kk]) <= N(pi/2) else N(pi)-abs(projection_angle_list[kk]) for kk in range(len(projection_angle_list))]
        
        if self._mumotModel._constantSystemSize == True:
            FixedPoints=[[PhiSubList[kk][Phi_stateVar1] for kk in range(len(PhiSubList)) if (0 <= re(PhiSubList[kk][Phi_stateVar1]) <= 1 and 0 <= re(PhiSubList[kk][Phi_stateVar2]) <= 1)], 
                         [PhiSubList[kk][Phi_stateVar2] for kk in range(len(PhiSubList)) if (0 <= re(PhiSubList[kk][Phi_stateVar1]) <= 1 and 0 <= re(PhiSubList[kk][Phi_stateVar2]) <= 1)]]
            Ell_width = [re(cos(N(pi/2)-projection_angle_list[kk])*sqrt(SOL_2ndOrdMomDictList[kk][M_2(eta_stateVar2**2)]/systemSize.subs(argDict)) + sin(N(pi/2)-projection_angle_list[kk])*sqrt(SOL_2ndOrdMomDictList[kk][M_2(eta_stateVar1**2)]/systemSize.subs(argDict))) for kk in range(len(SOL_2ndOrdMomDictList)) if (0 <= re(PhiSubList[kk][Phi_stateVar1]) <= 1 and 0 <= re(PhiSubList[kk][Phi_stateVar2]) <= 1)]
            Ell_height = [re(cos(projection_angle_list[kk])*sqrt(SOL_2ndOrdMomDictList[kk][M_2(eta_stateVar2**2)]/systemSize.subs(argDict)) + sin(projection_angle_list[kk])*sqrt(SOL_2ndOrdMomDictList[kk][M_2(eta_stateVar1**2)]/systemSize.subs(argDict))) for kk in range(len(SOL_2ndOrdMomDictList)) if (0 <= re(PhiSubList[kk][Phi_stateVar1]) <= 1 and 0 <= re(PhiSubList[kk][Phi_stateVar2]) <= 1)]
            #FixedPoints=[[realEQsol[kk][self._stateVariable1] for kk in range(len(realEQsol)) if (0 <= re(realEQsol[kk][self._stateVariable1]) <= 1 and 0 <= re(realEQsol[kk][self._stateVariable2]) <= 1)], 
            #             [realEQsol[kk][self._stateVariable2] for kk in range(len(realEQsol)) if (0 <= re(realEQsol[kk][self._stateVariable1]) <= 1 and 0 <= re(realEQsol[kk][self._stateVariable2]) <= 1)]]
        else:
            FixedPoints=[[PhiSubList[kk][Phi_stateVar1] for kk in range(len(PhiSubList))], 
                         [PhiSubList[kk][Phi_stateVar2] for kk in range(len(PhiSubList))]]
            Ell_width = [re(cos(N(pi/2)-projection_angle_list[kk])*sqrt(SOL_2ndOrdMomDictList[kk][M_2(eta_stateVar2**2)]/systemSize.subs(argDict)) + sin(N(pi/2)-projection_angle_list[kk])*sqrt(SOL_2ndOrdMomDictList[kk][M_2(eta_stateVar1**2)]/systemSize.subs(argDict))) for kk in range(len(SOL_2ndOrdMomDictList))]
            Ell_height = [re(cos(projection_angle_list[kk])*sqrt(SOL_2ndOrdMomDictList[kk][M_2(eta_stateVar2**2)]/systemSize.subs(argDict)) + sin(projection_angle_list[kk])*sqrt(SOL_2ndOrdMomDictList[kk][M_2(eta_stateVar1**2)]/systemSize.subs(argDict))) for kk in range(len(SOL_2ndOrdMomDictList))]
            #FixedPoints=[[realEQsol[kk][self._stateVariable1] for kk in range(len(realEQsol))], 
            #             [realEQsol[kk][self._stateVariable2] for kk in range(len(realEQsol))]]
            #Ell_width = [SOL_2ndOrdMomDictList[kk][M_2(eta_stateVar1**2)] for kk in range(len(SOL_2ndOrdMomDictList))]
            #Ell_height = [SOL_2ndOrdMomDictList[kk][M_2(eta_stateVar2**2)] for kk in range(len(SOL_2ndOrdMomDictList))] 
        
        # swap width and height of ellipse if width > height
        for kk in range(len(Ell_width)):
            ell_width_temp = Ell_width[kk]
            ell_height_temp = Ell_height[kk]
            if ell_width_temp > ell_height_temp:
                Ell_height[kk] = ell_width_temp
                Ell_width[kk] = ell_height_temp    
        
        FixedPoints.append(EVplot) 
        
        self._get_field2d("2d stream plot", 100) ## @todo: allow user to set mesh points with keyword
        
        if self._speed is not None:
            fig_stream=plt.streamplot(self._X, self._Y, self._Xdot, self._Ydot, color = self._speed, cmap = 'gray') ## @todo: define colormap by user keyword
        else:
            fig_stream=plt.streamplot(self._X, self._Y, self._Xdot, self._Ydot, color = 'k') ## @todo: define colormap by user keyword
        ells = [mpatch.Ellipse(xy=[FixedPoints[0][nn],FixedPoints[1][nn]], width=Ell_width[nn]/systemSize.subs(argDict), height=Ell_height[nn]/systemSize.subs(argDict), angle= round(angle_ell_list[nn],5)) for nn in range(len(FixedPoints[0]))]
        ax = plt.gca()
        for kk in range(len(ells)):
            ax.add_artist(ells[kk])
            ells[kk].set_alpha(0.25)
            if re(EVplot[kk][0]) < 0 and re(EVplot[kk][1]) < 0:
                Fcolor = line_color_list[1]
            elif re(EVplot[kk][0]) > 0 and re(EVplot[kk][1]) > 0:
                Fcolor = line_color_list[2]
            else:
                Fcolor = line_color_list[0]
            ells[kk].set_facecolor(Fcolor)
        if self._mumotModel._constantSystemSize == True:
            plt.fill_between([0,1], [1,0], [1,1], color='grey', alpha='0.25')            
            plt.xlim(0,1)
            plt.ylim(0,1)
        else:
            plt.xlim(0,self._X.max())
            plt.ylim(0,self._Y.max())
        
        _fig_formatting_2D(figure=fig_stream, xlab = self._xlab, specialPoints=FixedPoints, showFixedPoints=True, 
                           ax_reformat=False, curve_replot=False, ylab = self._ylab, fontsize=self._chooseFontSize)
#        plt.set_aspect('equal') ## @todo

        if self._showFixedPoints==True:
            with io.capture_output() as log:
                for kk in range(len(realEQsol)):
                    print('Fixed point'+str(kk+1)+':', realEQsol[kk], 'with eigenvalues:', str(EV[kk]),
                          'and eigenvectors:', str(Evects[kk]))
            self._logs.append(log)

## stream plot view on model
class MuMoTstreamView(MuMoTfieldView):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._generatingCommand = "mmt.MuMoTstreamView"

    def _plot_field(self):
        super()._plot_field()
        if self._showFixedPoints==True:
            realEQsol, eigList = self._get_fixedPoints2d()
            
            EV = []
            EVplot = []
            for kk in range(len(eigList)):
                EVsub = []
                for key in eigList[kk]:
                    if eigList[kk][key][0] >1:
                        for jj in range(eigList[kk][key][0]):
                            EVsub.append(key.evalf())
                    else:
                        EVsub.append(key.evalf())
                        
                EV.append(EVsub)
                if self._mumotModel._constantSystemSize == True:
                    if (0 <= re(realEQsol[kk][self._stateVariable1]) <= 1 and 0 <= re(realEQsol[kk][self._stateVariable2]) <= 1):
                        EVplot.append(EVsub)
                else:
                    EVplot.append(EVsub)
            
            #EV = []
            #EVplot = []
            #for kk in range(len(eigList)):
            #    EVsub = []
            #    for key in eigList[kk]:
            #        EVsub.append(key.evalf())
            #    EV.append(EVsub)
            #    if (0 <= re(realEQsol[kk][self._stateVariable1]) <= 1 and 0 <= re(realEQsol[kk][self._stateVariable2]) <= 1):
            #        EVplot.append(EVsub)

            if self._mumotModel._constantSystemSize == True:
                FixedPoints=[[realEQsol[kk][self._stateVariable1] for kk in range(len(realEQsol)) if (0 <= re(realEQsol[kk][self._stateVariable1]) <= 1 and 0 <= re(realEQsol[kk][self._stateVariable2]) <= 1)], 
                             [realEQsol[kk][self._stateVariable2] for kk in range(len(realEQsol)) if (0 <= re(realEQsol[kk][self._stateVariable1]) <= 1 and 0 <= re(realEQsol[kk][self._stateVariable2]) <= 1)]]
            else:
                FixedPoints=[[realEQsol[kk][self._stateVariable1] for kk in range(len(realEQsol))], 
                             [realEQsol[kk][self._stateVariable2] for kk in range(len(realEQsol))]]
            FixedPoints.append(EVplot)
        else:
            FixedPoints = None
            
        self._get_field2d("2d stream plot", 100) ## @todo: allow user to set mesh points with keyword
        if self._speed is not None:
            fig_stream=plt.streamplot(self._X, self._Y, self._Xdot, self._Ydot, color = self._speed, cmap = 'gray') ## @todo: define colormap by user keyword
        else:
            fig_stream=plt.streamplot(self._X, self._Y, self._Xdot, self._Ydot, color = 'k') ## @todo: define colormap by user keyword
        if self._mumotModel._constantSystemSize == True:
            plt.fill_between([0,1], [1,0], [1,1], color='grey', alpha='0.25')            
            plt.xlim(0,1)
            plt.ylim(0,1)
        else:
            plt.xlim(0,self._X.max())
            plt.ylim(0,self._Y.max())
        
        _fig_formatting_2D(figure=fig_stream, xlab = self._xlab, specialPoints=FixedPoints, showFixedPoints=self._showFixedPoints, ax_reformat=False, curve_replot=False,
                   ylab = self._ylab, fontsize=self._chooseFontSize)
#        plt.set_aspect('equal') ## @todo

        if self._showFixedPoints==True:
            with io.capture_output() as log:
                for kk in range(len(realEQsol)):
                    print('Fixed point'+str(kk+1)+':', realEQsol[kk], 'with eigenvalues:', str(EV[kk]))
            self._logs.append(log)


## vector plot view on model
class MuMoTvectorView(MuMoTfieldView):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._generatingCommand = "mmt.MuMoTvectorView"

    def _plot_field(self):
        super()._plot_field()
        if self._stateVariable3 == None:
            if self._showFixedPoints==True:
                realEQsol, eigList = self._get_fixedPoints2d()
                
                EV = []
                EVplot = []
                for kk in range(len(eigList)):
                    EVsub = []
                    for key in eigList[kk]:
                        if eigList[kk][key][0] >1:
                            for jj in range(eigList[kk][key][0]):
                                EVsub.append(key.evalf())
                        else:
                            EVsub.append(key.evalf())
                            
                    EV.append(EVsub)
                    if self._mumotModel._constantSystemSize == True:
                        if (0 <= re(realEQsol[kk][self._stateVariable1]) <= 1 and 0 <= re(realEQsol[kk][self._stateVariable2]) <= 1):
                            EVplot.append(EVsub)
                    else:
                        EVplot.append(EVsub)

                #EV = []
                #EVplot = []
                #for kk in range(len(eigList)):
                #    EVsub = []
                #    for key in eigList[kk]:
                #        EVsub.append(key.evalf())
                #    EV.append(EVsub)
                #    if (0 <= re(realEQsol[kk][self._stateVariable1]) <= 1 and 0 <= re(realEQsol[kk][self._stateVariable2]) <= 1):
                #        EVplot.append(EVsub)
                
                if self._mumotModel._constantSystemSize == True:
                    FixedPoints=[[realEQsol[kk][self._stateVariable1] for kk in range(len(realEQsol)) if (0 <= re(realEQsol[kk][self._stateVariable1]) <= 1 and 0 <= re(realEQsol[kk][self._stateVariable2]) <= 1)], 
                                 [realEQsol[kk][self._stateVariable2] for kk in range(len(realEQsol)) if (0 <= re(realEQsol[kk][self._stateVariable1]) <= 1 and 0 <= re(realEQsol[kk][self._stateVariable2]) <= 1)]]
                else:
                    FixedPoints=[[realEQsol[kk][self._stateVariable1] for kk in range(len(realEQsol))], 
                                 [realEQsol[kk][self._stateVariable2] for kk in range(len(realEQsol))]]
                FixedPoints.append(EVplot)
            else:
                FixedPoints = None
            
            self._get_field2d("2d vector plot", 10) ## @todo: allow user to set mesh points with keyword
            fig_vector=plt.quiver(self._X, self._Y, self._Xdot, self._Ydot, units='width', color = 'black') ## @todo: define colormap by user keyword

            if self._mumotModel._constantSystemSize == True:
                plt.fill_between([0,1], [1,0], [1,1], color='grey', alpha='0.25')
            else:
                plt.xlim(0,self._X.max())
                plt.ylim(0,self._Y.max())
            _fig_formatting_2D(figure=fig_vector, xlab = self._xlab, specialPoints=FixedPoints, showFixedPoints=self._showFixedPoints, ax_reformat=False, curve_replot=False,
                   ylab = self._ylab, fontsize=self._chooseFontSize)
    #        plt.set_aspect('equal') ## @todo
            if self._showFixedPoints==True:
                with io.capture_output() as log:
                    for kk in range(len(realEQsol)):
                        print('Fixed point'+str(kk+1)+':', realEQsol[kk], 'with eigenvalues:', str(EV[kk]))
                self._logs.append(log)
        
        else:
            if self._showFixedPoints==True:
                realEQsol, eigList = self._get_fixedPoints3d()
                EV = []
                EVplot = []
                for kk in range(len(eigList)):
                    EVsub = []
                    for key in eigList[kk]:
                        if eigList[kk][key][0] >1:
                            for jj in range(eigList[kk][key][0]):
                                EVsub.append(key.evalf())
                        else:
                            EVsub.append(key.evalf())
                            
                    EV.append(EVsub)
                    if self._mumotModel._constantSystemSize == True:
                        if (0 <= re(realEQsol[kk][self._stateVariable1]) <= 1 and 0 <= re(realEQsol[kk][self._stateVariable2]) <= 1 and 0 <= re(realEQsol[kk][self._stateVariable3]) <= 1):
                            EVplot.append(EVsub)
                    else:
                        EVplot.append(EVsub)
                    
                if self._mumotModel._constantSystemSize == True:
                    FixedPoints=[[realEQsol[kk][self._stateVariable1] for kk in range(len(realEQsol)) if (0 <= re(realEQsol[kk][self._stateVariable1]) <= 1) and (0 <= re(realEQsol[kk][self._stateVariable2]) <= 1) and (0 <= re(realEQsol[kk][self._stateVariable3]) <= 1)], 
                                 [realEQsol[kk][self._stateVariable2] for kk in range(len(realEQsol)) if (0 <= re(realEQsol[kk][self._stateVariable1]) <= 1) and (0 <= re(realEQsol[kk][self._stateVariable2]) <= 1) and (0 <= re(realEQsol[kk][self._stateVariable3]) <= 1)],
                                 [realEQsol[kk][self._stateVariable3] for kk in range(len(realEQsol)) if (0 <= re(realEQsol[kk][self._stateVariable1]) <= 1) and (0 <= re(realEQsol[kk][self._stateVariable2]) <= 1) and (0 <= re(realEQsol[kk][self._stateVariable3]) <= 1)]]
                else:
                    FixedPoints=[[realEQsol[kk][self._stateVariable1] for kk in range(len(realEQsol))], 
                                 [realEQsol[kk][self._stateVariable2] for kk in range(len(realEQsol))],
                                 [realEQsol[kk][self._stateVariable3] for kk in range(len(realEQsol))]]
                FixedPoints.append(EVplot)
            else:
                FixedPoints = None
                
            self._get_field3d("3d vector plot", 10)
            ax = self._figure.gca(projection = '3d')
            fig_vec3d=ax.quiver(self._X, self._Y, self._Z, self._Xdot, self._Ydot, self._Zdot, length = 0.01, color = 'black') ## @todo: define colormap by user keyword; normalise off maximum value in self._speed, and meshpoints?
            _fig_formatting_3D(figure=fig_vec3d, xlab= self._xlab, ylab= self._ylab, zlab= self._zlab, specialPoints=FixedPoints,
                               showFixedPoints=self._showFixedPoints, ax_reformat=True, showPlane=self._mumotModel._constantSystemSize)
#           plt.set_aspect('equal') ## @todo

            if self._showFixedPoints==True:
                with io.capture_output() as log:
                    for kk in range(len(realEQsol)):
                        print('Fixed point'+str(kk+1)+':', realEQsol[kk], 'with eigenvalues:', str(EV[kk]))
                self._logs.append(log)


## bifurcation view on model 
class MuMoTbifurcationView(MuMoTview):
    _pyDSmodel = None
    _bifurcationParameter = None
    _stateVariable1 = None
    _stateVariable2 = None
    
    ## Plotting method to use
    _plottingMethod = None
    
    def __init__(self, model, controller, bifurcationParameter, stateVariable1, stateVariable2 = None, 
                 figure = None, params = None, **kwargs):
        super().__init__(model, controller, figure, params, **kwargs)
        self._generatingCommand = "mmt.MuMoTbifurcationView"
        bifurcationParameter = self._pydstoolify(bifurcationParameter)
        stateVariable1 = self._pydstoolify(stateVariable1)
        stateVariable2 = self._pydstoolify(stateVariable2)

        paramDict = {}
        initialRateValue = INITIAL_RATE_VALUE ## @todo was 1 (choose initial values sensibly)
        rateLimits = (0, RATE_BOUND) ## @todo choose limit values sensibly
        rateStep = RATE_STEP ## @todo choose rate step sensibly
        for rate in self._mumotModel._rates:
            paramDict[self._pydstoolify(rate)] = initialRateValue ## @todo choose initial values sensibly
        paramDict[self._pydstoolify(self._mumotModel._systemSize)] = 1 ## @todo choose system size sensibly
        
        if 'fontsize' in kwargs:
            self._chooseFontSize = kwargs['fontsize']
        else:
            self._chooseFontSize=None
            
        if 'xlab' in kwargs:
            self._xlab = kwargs['xlab']
        else:
            self._xlab=None
            
        if 'ylab' in kwargs:
            self._ylab = kwargs['ylab']
        else:
            self._ylab=None
            
        self._bifInit = kwargs.get('BifParInit', 5)
        
        tmpInitSV = kwargs.get('initSV', [])
        self._initSV= []
        if tmpInitSV != []:
            assert (len(tmpInitSV) == len(self._mumotModel._reactants)),"Number of state variables and initial conditions must coincide!"
            for pair in tmpInitSV:
                self._initSV.append([self._pydstoolify(pair[0]), pair[1]])
        else:
            if kwargs.get('initRandom', False) == True:
                for reactant in self._mumotModel._reactants:
                    self._initSV.append([self._pydstoolify(reactant), round(np.random.rand(), 2)])
            else:
                for reactant in self._mumotModel._reactants:
                    self._initSV.append([self._pydstoolify(reactant), 0.0])
                
        with io.capture_output() as log:      
            name = 'MuMoT Model' + str(id(self))
            self._pyDSmodel = dst.args(name = name)
            self._pyDSmodel.pars = paramDict
            varspecs = {}
            for reactant in self._mumotModel._reactants:
                varspecs[self._pydstoolify(reactant)] = self._pydstoolify(self._mumotModel._equations[reactant])
            self._pyDSmodel.varspecs = varspecs
    
            if model._systemSize != None:
                ## @todo: shouldn't allow system size to be varied?
                pass
    #                self._paramValues.append(1)
    #                self._paramNames.append(str(self._systemSize))
    #                widget = widgets.FloatSlider(value = 1, min = _rateLimits[0], max = _rateLimits[1], step = _rateStep, description = str(self._systemSize), continuous_update = False)
    #                widget.on_trait_change(self._replot_bifurcation2D, 'value')
    #                display(widget)
            else:
                print('Cannot attempt bifurcation plot until system size is set, using substitute()')
                return
            
            if stateVariable2 != None:
                ## 3-d bifurcation diagram (@todo: currently unsupported)
                assert True #was 'false' before. @todo: Specify assertion rule.
                
            # Prepare the system to start close to a steady state
            self._bifurcationParameter = bifurcationParameter
            self._LabelX = self._bifurcationParameter if self._xlab == None else self._xlab
            try:
                stateVariable1.index('-')
                self._stateVariable1 = stateVariable1[:stateVariable1.index('-')]
                self._stateVariable2 = stateVariable1[stateVariable1.index('-')+1:]
                self._LabelY = self._stateVariable1+'-'+self._stateVariable2 if self._ylab == None else self._ylab
            except ValueError:
                self._stateVariable1 = stateVariable1
                self._stateVariable2 = stateVariable2
                self._LabelY = self._stateVariable1 if self._ylab == None else self._ylab
    #            self._pyDSode.set(pars = {bifurcationParameter: 0} )       ## Lower bound of the bifurcation parameter (@todo: set dynamically)
    #            self._pyDSode.set(pars = self._pyDSmodel.pars )       ## Lower bound of the bifurcation parameter (@todo: set dynamically)
    #            self._pyDSode.pars = {bifurcationParameter: 0}             ## Lower bound of the bifurcation parameter (@todo: set dynamically?)
            initconds = {stateVariable1: self._pyDSmodel.pars[self._pydstoolify(self._mumotModel._systemSize)] / len(self._mumotModel._reactants)} ## @todo: guess where steady states are?
            
            self._pyDSmodel.ics   = {}
            for kk in range(len(self._initSV)):
                self._pyDSmodel.ics[self._initSV[kk][0]] = self._initSV[kk][1]  #{'A': 0.1, 'B': 0.9 }  
            print('Initial conditions chosen for state variables: ',self._pyDSmodel.ics)   
    #            self._pyDSode.set(ics = initconds)
            self._pyDSode = dst.Generator.Vode_ODEsystem(self._pyDSmodel)  
            self._pyDSode.set(pars = {bifurcationParameter: self._bifInit})      ## @@todo remove magic number
            self._pyDScont = dst.ContClass(self._pyDSode)              # Set up continuation class 
            ## @todo: add self._pyDScontArgs to __init__()
            self._pyDScontArgs = dst.args(name='EQ1', type='EP-C')     # 'EP-C' stands for Equilibrium Point Curve. The branch will be labeled 'EQ1'.
            self._pyDScontArgs.freepars     = [bifurcationParameter]   # control parameter(s) (should be among those specified in self._pyDSmodel.pars)
            self._pyDScontArgs.MaxNumPoints = kwargs.get('ContMaxNumPoints',450)    ## The following 3 parameters are set after trial-and-error @todo: how to automate this?
            self._pyDScontArgs.MaxStepSize  = 1e-1
            self._pyDScontArgs.MinStepSize  = 1e-5
            self._pyDScontArgs.StepSize     = 2e-3
            self._pyDScontArgs.LocBifPoints = ['LP', 'BP']        ## @todo WAS 'LP' (detect limit points / saddle-node bifurcations)
            self._pyDScontArgs.SaveEigen    = True             # to tell unstable from stable branches
#            self._pyDScontArgs.CalcStab     = True
        self._logs.append(log)
        
#            self._bifurcation2Dfig = plt.figure(1)                    

        #if kwargs != None:
        #    self._plottingMethod = kwargs.get('plottingMethod', 'pyDS')
        #else:
        #    self._plottingMethod = 'pyDS'
        
        self._plottingMethod = kwargs.get('plottingMethod', 'mumot')
        self._plot_bifurcation()
            

    def _plot_bifurcation(self):
        self._resetErrorMessage()
        with io.capture_output() as log:
            self._log("bifurcation analysis")
            self._pyDScont.newCurve(self._pyDScontArgs)
            try:
                try:
                    self._pyDScont['EQ1'].backward()
                except:
                    self._showErrorMessage('Continuation failure (backward)<br>')
                try:
                    self._pyDScont['EQ1'].forward()              ## @todo: how to choose direction?
                except:
                    self._showErrorMessage('Continuation failure (forward)<br>')
            except ZeroDivisionError:
                self._showErrorMessage('Division by zero<br>')                
    #            self._pyDScont['EQ1'].info()
        
            if self._plottingMethod.lower() == 'mumot':
                ## use internal plotting routines: now supported!   
                #self._stateVariable2 == None:
                # 2-d bifurcation diagram
                self._specialPoints=[]  #todo: modify to include several equations not only EQ1
                k_iter=1
                self.sPoints_X=[] #bifurcation parameter
                self.sPoints_Y=[] #state variable 1
                self.sPoints_Labels=[]
                
                #while self._pyDScont['EQ1'].getSpecialPoint('BP'+str(k_iter)):
                #    self.sPoints_X.append(self._pyDScont['EQ1'].getSpecialPoint('BP'+str(k_iter))[2])
                #    self.sPoints_Y.append(self._pyDScont['EQ1'].getSpecialPoint('BP'+str(k_iter))[0])
                #    self.sPoints_Z.append(self._pyDScont['EQ1'].getSpecialPoint('BP'+str(k_iter))[1])
                #    self.sPoints_Labels.append('BP'+str(k_iter))
                #    k_iter+=1
                #k_iter=1
                #while self._pyDScont['EQ1'].getSpecialPoint('LP'+str(k_iter)):
                #    self.sPoints_X.append(self._pyDScont['EQ1'].getSpecialPoint('LP'+str(k_iter))[2])
                #    self.sPoints_Y.append(self._pyDScont['EQ1'].getSpecialPoint('LP'+str(k_iter))[0])
                #    self.sPoints_Z.append(self._pyDScont['EQ1'].getSpecialPoint('LP'+str(k_iter))[1])
                #    self.sPoints_Labels.append('LP'+str(k_iter))
                #    k_iter+=1
    
                
                
                if self._stateVariable2 != None:
                    try:
                        self.sPoints_Z=[] #state variable 2
                        self._YDATA = (self._pyDScont['EQ1'].sol[self._stateVariable1] -
                                  self._pyDScont['EQ1'].sol[self._stateVariable2])
                        while self._pyDScont['EQ1'].getSpecialPoint('BP'+str(k_iter)):
                            self.sPoints_X.append(self._pyDScont['EQ1'].getSpecialPoint('BP'+str(k_iter))[self._bifurcationParameter])
                            self.sPoints_Y.append(self._pyDScont['EQ1'].getSpecialPoint('BP'+str(k_iter))[self._stateVariable1])
                            self.sPoints_Z.append(self._pyDScont['EQ1'].getSpecialPoint('BP'+str(k_iter))[self._stateVariable2])
                            self.sPoints_Labels.append('BP'+str(k_iter))
                            k_iter+=1
                        k_iter=1
                        while self._pyDScont['EQ1'].getSpecialPoint('LP'+str(k_iter)):
                            self.sPoints_X.append(self._pyDScont['EQ1'].getSpecialPoint('LP'+str(k_iter))[self._bifurcationParameter])
                            self.sPoints_Y.append(self._pyDScont['EQ1'].getSpecialPoint('LP'+str(k_iter))[self._stateVariable1])
                            self.sPoints_Z.append(self._pyDScont['EQ1'].getSpecialPoint('LP'+str(k_iter))[self._stateVariable2])
                            self.sPoints_Labels.append('LP'+str(k_iter))
                            k_iter+=1
                        self._specialPoints=[self.sPoints_X, 
                                             np.asarray(self.sPoints_Y)-np.asarray(self.sPoints_Z), 
                                             self.sPoints_Labels]
                    except TypeError:
                        print('Continuation failed; try with different parameters.')
                    
                else:
                    try:
                        self._YDATA = self._pyDScont['EQ1'].sol[self._stateVariable1]
                        while self._pyDScont['EQ1'].getSpecialPoint('BP'+str(k_iter)):
                            self.sPoints_X.append(self._pyDScont['EQ1'].getSpecialPoint('BP'+str(k_iter))[self._bifurcationParameter])
                            self.sPoints_Y.append(self._pyDScont['EQ1'].getSpecialPoint('BP'+str(k_iter))[self._stateVariable1])
                            self.sPoints_Labels.append('BP'+str(k_iter))
                            k_iter+=1
                        k_iter=1
                        while self._pyDScont['EQ1'].getSpecialPoint('LP'+str(k_iter)):
                            self.sPoints_X.append(self._pyDScont['EQ1'].getSpecialPoint('LP'+str(k_iter))[self._bifurcationParameter])
                            self.sPoints_Y.append(self._pyDScont['EQ1'].getSpecialPoint('LP'+str(k_iter))[self._stateVariable1])
                            self.sPoints_Labels.append('LP'+str(k_iter))
                            k_iter+=1
                        
                        self._specialPoints=[self.sPoints_X, self.sPoints_Y, self.sPoints_Labels]    
                    except TypeError:
                        print('Continuation failed; try with different parameters.')
                
                #The following was an attempt to include also EQ2 if a BP or LP was found using EQ1    
                #if self._pyDScont['EQ1'].getSpecialPoint('BP1'):
                #    self._pyDSode.set(pars = {self._bifurcationParameter: 5} )
                #    self._pyDScontArgs.freepars     = [self._bifurcationParameter]
                #    self._pyDScontArgs = dst.args(name='EQ2', type='EP-C')
                #    self._pyDScontArgs.initpoint    = 'EQ1:BP1'
                #    
                #   self._pyDScont.newCurve(self._pyDScontArgs)
                #   try:
                #        try:
                #            self._pyDScont['EQ2'].backward()
                #        except:
                #            self._showErrorMessage('Continuation failure (backward)<br>')
                #        try:
                #            self._pyDScont['EQ2'].forward()
                #        except:
                #            self._showErrorMessage('Continuation failure (forward)<br>')
                #    except ZeroDivisionError:
                #        self._showErrorMessage('Division by zero<br>')  
                
                
                #    self.sPoints_X.append(self._pyDScont['EQ1'].getSpecialPoint('BP'+str(k_iter))[2])
                #    self.sPoints_Y.append(self._pyDScont['EQ1'].getSpecialPoint('BP'+str(k_iter))[0])
                #    self.sPoints_Z.append(self._pyDScont['EQ1'].getSpecialPoint('BP'+str(k_iter))[1])
                #    self.sPoints_Labels.append('BP'+str(k_iter))
                
                #elif self._pyDScont['EQ2'].getSpecialPoint('LP1'):
                #    self.sPoints_X.append(self._pyDScont['EQ1'].getSpecialPoint('LP'+str(k_iter))[2])
                #    self.sPoints_Y.append(self._pyDScont['EQ1'].getSpecialPoint('LP'+str(k_iter))[0])
                #    self.sPoints_Z.append(self._pyDScont['EQ1'].getSpecialPoint('LP'+str(k_iter))[1])
                #    self.sPoints_Labels.append('LP'+str(k_iter))
                #    k_iter+=1
                
                print('Special Points on curve: ', self._specialPoints)
                
                plt.clf()
                _fig_formatting_2D(xdata=[self._pyDScont['EQ1'].sol[self._bifurcationParameter]], 
                                ydata=[self._YDATA],
                                xlab = self._LabelX, 
                                ylab = self._LabelY,
                                specialPoints=self._specialPoints, 
                                eigenvalues=[np.array([self._pyDScont['EQ1'].sol[kk].labels['EP']['data'].evals for kk in range(len(self._pyDScont['EQ1'].sol[self._stateVariable1]))])], 
                                ax_reformat=False, curve_replot=False, fontsize=self._chooseFontSize)

#                self._pyDScont.plot.fig1.axes1.axes.set_title('Bifurcation Diagram')
                #else:
                #    pass
                #assert false
            else:
                if self._plottingMethod.lower() != 'pyds':
                    self._showErrorMessage('Unknown plotType argument: using default pyDS tool plotting<br>')    
                if self._stateVariable2 == None:
                    # 2-d bifurcation diagram
                    if self._silent == True:
                        #assert false ## @todo: enable when Thomas implements in-housse plotting routines
                        self._pyDScont.display([self._bifurcationParameter, self._stateVariable1], axes = None, stability = True)
                    else:
                        self._pyDScont.display([self._bifurcationParameter, self._stateVariable1], stability = True, figure = self._figureNum)
    #                self._pyDScont.plot.fig1.axes1.axes.set_title('Bifurcation Diagram')
                else:
                    pass
        self._logs.append(log)

    def _replot_bifurcation(self):
        for name, value in self._controller._widgetsFreeParams.items():
            self._pyDSmodel.pars[name] = value.value
 
        self._pyDScont.plot.clearall()
        
#        self._pyDSmodel.ics      = {'A': 0.1, 'B': 0.9 }    ## @todo: replace           
        self._pyDSode = dst.Generator.Vode_ODEsystem(self._pyDSmodel)  ## @todo: add to __init__()
        self._pyDSode.set(pars = {self._bifurcationParameter: self._bifInit} )                       ## @todo remove magic number
        self._pyDScont = dst.ContClass(self._pyDSode)              ## Set up continuation class (@todo: add to __init__())
##        self._pyDScont.newCurve(self._pyDScontArgs)
#        self._pyDScont['EQ1'].reset(self._pyDSmodel.pars)
#        self._pyDSode.set(pars = self._pyDSmodel.pars)
#        self._pyDScont['EQ1'].reset()
#        self._pyDScont.update(self._pyDScontArgs)                         ## @todo: what does this do?
        self._plot_bifurcation()

    # utility function to mangle variable names in equations so they are accepted by PyDStool
    def _pydstoolify(self, equation):
        equation = str(equation)
        equation = equation.replace('{', '')
        equation = equation.replace('}', '')
        equation = equation.replace('_', '')
        equation = equation.replace('\\', '')
        
        return equation

## agent on networks view on model 
class MuMoTmultiagentView(MuMoTview):
    _colors = None
    _probabilities = None
    ## structure to store the communication network
    _graph = None
    ## type of network used in the M-A simulation
    _netType = None
    ## network parameter which varies with respect to each type of network
    ## (for Erdos-Renyi is linking probability, for Barabasi-Albert is the number of edge per new node, for spatial is the communication range)
    _netParam = None
    ## speed of the particle on one timestep (only for dynamic netType)
    _particleSpeed = None
    ## corelatedness in the random walk motion (only for dynamic netType)
    _motionCorrelatedness = None
    ## list of agents involved in the simulation
    _agents = None
    ## list of agents' positions
    _positions = None
    ## Arena size: width
    _arena_width = 1
    ## Arena size: height
    _arena_height = 1
    ## the system state at the start of the simulation (timestep zero)
    _initialState = None
    ## random seed
    _randomSeed = None
    ## number of simulation timesteps
    _maxTime = None
    ## time scaling (i.e. lenght of each timestep)
    _timestepSize = None
    ## dictionary of rates
    _ratesDict = None
    ## visualisation type
    _visualisationType = None
    ## visualise the agent trace (on moving particles)
    _showTrace = None
    ## visualise the agent trace (on moving particles)
    _showInteractions = None
    ## realtimePlot flag (TRUE = the plot is updated each timestep of the simulation; FALSE = it is updated once at the end of the simulation)
    _realtimePlot = None
    ## latest computed results
    _latestResults = None

    def __init__(self, model, controller, MAParams, figure = None, rates = None, **kwargs):
        super().__init__(model=model, controller=controller, figure=figure, params=rates, **kwargs)

        with io.capture_output() as log:
                      
            if self._controller == None:
                # storing the rates for each rule
                ## @todo moving it to general method?
                self._ratesDict = {}
                rates_input_dict = dict( rates )
                for key in rates_input_dict.keys():
                    rates_input_dict[str(process_sympy(str(key)))] = rates_input_dict.pop(key) # replace the dictionary key with the str of the SymPy symbol
                # create the self._ratesDict 
                for rule in self._mumotModel._rules:
                    self._ratesDict[str(rule.rate)] = rates_input_dict[str(rule.rate)] 
            
            # storing the initial state
            self._initialState = {}
            for state,pop in MAParams["initialState"].items():
                self._initialState[process_sympy(str(state))] = pop # convert string into SymPy symbol
                #self._initialState[state] = pop
            self._maxTime = MAParams["maxTime"]
            self._randomSeed = MAParams["randomSeed"]
            self._visualisationType = MAParams["visualisationType"]
            self._netType = _decodeNetworkTypeFromString(MAParams['netType'])
            self._netParam = MAParams['netParam']
            self._motionCorrelatedness = MAParams['motionCorrelatedness']
            self._particleSpeed = MAParams['particleSpeed']
            self._timestepSize = MAParams.get('timestepSize',1)
            self._showTrace = MAParams.get('showTrace',False)
            self._showInteractions = MAParams.get('showInteractions',False)
            self._realtimePlot = MAParams.get('realtimePlot', False)
            
            self._initGraph(graphType=self._netType, numNodes=sum(self._initialState.values()), netParam=self._netParam)

            # map colouts to each reactant
            #colors = cm.rainbow(np.linspace(0, 1, len(self._mumotModel._reactants) ))  # @UndefinedVariable
            self._colors = {}
            i = 0
            for state in sorted(self._initialState.keys(), key=str): #sorted(self._mumotModel._reactants, key=str):
                self._colors[state] = line_color_list[i] 
                i += 1            
            
        self._logs.append(log)
        if not self._silent:
            self._plot_timeEvolution()
        
    def _print_standalone_view_cmd(self):
        MAParams = {}
        initState_str = {}
        for state,pop in self._initialState.items():
            initState_str[str(state)] = pop
        MAParams["initialState"] = initState_str 
        MAParams["maxTime"] = self._maxTime 
        MAParams["randomSeed"] = self._randomSeed
        MAParams["visualisationType"] = self._visualisationType
        MAParams['netType'] = _encodeNetworkTypeToString(self._netType)
        MAParams['netParam'] = self._netParam 
        MAParams['motionCorrelatedness'] = self._motionCorrelatedness
        MAParams['particleSpeed'] = self._particleSpeed
        MAParams['timestepSize'] = self._timestepSize
        MAParams['showTrace'] = self._showTrace
        MAParams['showInteractions'] = self._showInteractions
#         sortedDict = "{"
#         for key,value in sorted(MAParams.items()):
#             sortedDict += "'" + key + "': " + str(value) + ", "
#         sortedDict += "}"
        print( "mmt.MuMoTmultiagentView(model1, None, MAParams = " + str(MAParams) + ", rates = " + str( list(self._ratesDict.items()) ) + " )")
    
    ## reads the new parameters (in case they changed in the controller)
    ## this function should only update local parameters and not compute data
    def _update_params(self):
        if self._controller != None:
            # getting the rates
            ## @todo moving it to general method?
            self._ratesDict = {}
            for rule in self._mumotModel._rules:
                self._ratesDict[str(rule.rate)] = self._controller._widgetsFreeParams[str(rule.rate)].value
            # getting other parameters specific to M-A view
            for state in self._initialState.keys():
                self._initialState[state] = self._controller._widgetsExtraParams['init'+str(state)].value
            #numNodes = sum(self._initialState.values())
            self._randomSeed = self._controller._widgetsExtraParams['randomSeed'].value
            self._visualisationType = self._controller._widgetsPlotOnly['visualisationType'].value
            self._maxTime = self._controller._widgetsExtraParams['maxTime'].value
            self._netType = self._controller._widgetsExtraParams['netType'].value
            self._netParam = self._controller._widgetsExtraParams['netParam'].value
            self._motionCorrelatedness = self._controller._widgetsExtraParams['motionCorrelatedness'].value
            self._particleSpeed = self._controller._widgetsExtraParams['particleSpeed'].value
            self._timestepSize = self._controller._widgetsExtraParams['timestepSize'].value
            self._showTrace = self._controller._widgetsPlotOnly['showTrace'].value
            self._showInteractions = self._controller._widgetsPlotOnly['showInteractions'].value
            self._realtimePlot = self._controller._widgetsExtraParams['realtimePlot'].value

    
    def _plot_timeEvolution(self):
        with io.capture_output() as log:
#         if True:
            # update parameters (needed only if there's a controller)
            self._update_params()
            self._log("Multiagent simulation")
            self._print_standalone_view_cmd()

            # init the random seed
            np.random.seed(self._randomSeed)
            
            # init the network
            self._initGraph(graphType=self._netType, numNodes=sum(self._initialState.values()), netParam=self._netParam)
            
            self._convertRatesIntoProbabilities(self._mumotModel._reactants, self._mumotModel._rules)

            # Clearing the plot and setting the axes
            self._initFigure()
            
            self._latestResults = self._runMultiagent()
            print("Temporal evolution per state: " + str(self._latestResults[0]))
            
            ## Final Plot
            if not self._realtimePlot:
                self._updateMultiagentFigure(0, self._latestResults[0], positionHistory=self._latestResults[1], pos_layout=self._latestResults[2])
            
        self._logs.append(log)      
    
    def _redrawOnly(self):
        self._update_params()
        self._initFigure()
        self._updateMultiagentFigure(0, self._latestResults[0], positionHistory=self._latestResults[1], pos_layout=self._latestResults[2])
        
    def _runMultiagent(self):
        # init the controller variables
        self._initMultiagent()
        
        # init logging structs
#         historyState = []
#         historyState.append(initialState)
        evo = {}
        for state,pop in self._initialState.items():
            evo[state] = []
            evo[state].append(pop)
            
        dynamicNetwork = self._netType == NetworkType.DYNAMIC
        if dynamicNetwork:
            positionHistory = []
            for _ in np.arange(sum(self._initialState.values())):
                positionHistory.append( [] )
        else:
            positionHistory = None
            
        # init progress bar
        if self._controller != None: self._controller._progressBar.max = self._maxTime
        
        # store the graph layout (only for 'graph' visualisation)
        if (not dynamicNetwork): # and self._visualisationType == "graph":
            pos_layout = nx.circular_layout(self._graph)
        else:
            pos_layout = None
        
        for i in np.arange(1, self._maxTime+1):
            #print("Time: " + str(i))
            if self._controller != None: self._controller._progressBar.value = i
            if self._controller != None: self._controller._progressBar.description = "Loading " + str(round(i/self._maxTime*100)) + "%:"
            if dynamicNetwork: # and self._showTrace:
                for idx, _ in enumerate(self._agents): # second element _ is the agent (unused)
                    positionHistory[idx].append( self._positions[idx] )
            
            currentState = self._stepMultiagent()
                    
#             historyState.append(currentState)
            for state,pop in currentState.items():
                evo[state].append(pop)
            
            ## Plotting
            if self._realtimePlot:
                self._updateMultiagentFigure(i, evo, positionHistory=positionHistory, pos_layout=pos_layout)

                
        if self._controller != None: self._controller._progressBar.description = "Completed 100%:"
#         print("State distribution each timestep: " + str(historyState))
        return (evo, positionHistory, pos_layout)
        
    def _initFigure(self):
        if not self._silent:
            plt.figure(self._figureNum)
            plt.clf()

        if (self._visualisationType == 'evo'):
            plt.axes().set_aspect('auto')
            # create the frame
            totAgents = sum(self._initialState.values())
#                     self._plot.axis([0, self._maxTime, 0, totAgents])
            plt.xlim((0, self._maxTime))
            plt.ylim((0, totAgents))
            #self._figure.show()
            _fig_formatting_2D(self._figure, xlab="Time", ylab="Reactants", curve_replot=(not self._silent))
        elif self._visualisationType == "graph": #and self._netType == NetworkType.DYNAMIC:
            plt.axes().set_aspect('equal')
        elif (self._visualisationType == "final"):
#             plt.axes().set_aspect('equal') #for piechart
            plt.axes().set_aspect('auto') # for barchart
            plt.ylim((0, sum(self._initialState.values())))
    
    
    def _updateMultiagentFigure(self, i, evo, positionHistory, pos_layout):
        if (self._visualisationType == "evo"):
            # If realtime-plot mode, draw only the last timestep rather than overlay all
            if (i>1):
                xdata = []
                ydata = []
                for state in sorted(self._initialState.keys(), key=str):
                    xdata.append( list(np.arange(len(evo[state]))) )
                    ydata.append( evo[state] )
                    ## @todo replot only the last part (rather than all the line)
#                     xdata.append( [i-1,i] )
#                     pop = evo[state]
#                     ydata.append( pop[len(pop)-2:len(pop)] )
                    #plt.plot(evo[state], color=self._colors[state])
                _fig_formatting_2D(xdata=xdata, ydata=ydata, curve_replot=False)
            else: # otherwise, plot all time-evolution
                xdata = []
                ydata = []
                labels = []
                for state in sorted(self._initialState.keys(), key=str):
                    xdata.append( list(np.arange(len(evo[state]))) )
                    ydata.append(evo[state])
                    labels.append(state)
                #xdata=[list(np.arange(len(list(evo.values())[0])))]*len(evo.values()), ydata=list(evo.values()), curvelab=list(evo.keys())
                    #plt.plot(evo[state], color=self._colors[state])
                _fig_formatting_2D(xdata=xdata, ydata=ydata, curvelab=labels, curve_replot=False)

        elif (self._visualisationType == "graph"):
            self._initFigure()
            #plt.clf()
            #plt.axes().set_aspect('equal')
            if self._netType == NetworkType.DYNAMIC:
                plt.xlim((0, 1))
                plt.ylim((0, 1))
                #plt.axes().set_aspect('equal')
#                     xs = [p[0] for p in positions]
#                     ys = [p[1] for p in positions]
#                     plt.plot(xs, ys, 'o' )
                xs = {}
                ys = {}
                for state in self._initialState.keys():
                    xs[state] = []
                    ys[state] = []
                for a in np.arange(len(self._positions)):
                    xs[self._agents[a]].append( self._positions[a][0] )
                    ys[self._agents[a]].append( self._positions[a][1] )
                    
                    if self._showInteractions:
                        for n in self._getNeighbours(a, self._positions, self._netParam): 
                            plt.plot((self._positions[a][0], self._positions[n][0]),(self._positions[a][1], self._positions[n][1]), '-', c='y')
                    
                    if self._showTrace:
                        trace_xs = [p[0] for p in positionHistory[a] ]
                        trace_ys = [p[1] for p in positionHistory[a] ]
                        trace_xs.append( self._positions[a][0] )
                        trace_ys.append( self._positions[a][1] )
                        plt.plot( trace_xs, trace_ys, '-', c='0.6') 
                for state in self._initialState.keys():
                    plt.plot(xs.get(state,[]), ys.get(state,[]), 'o', c=self._colors[state] )
            else:
                stateColors=[]
                for n in self._graph.nodes():
                    stateColors.append( self._colors.get( self._agents[n], 'w') ) 
                nx.draw(self._graph, pos_layout, node_color=stateColors, with_labels=True)
                # plot legend
                markers = [plt.Line2D([0,0],[0,0],color=color, marker='o', linestyle='', markersize=15) for color in self._colors.values()]
                plt.legend(markers, self._colors.keys(), bbox_to_anchor=(0.85, 0.95), loc=2, borderaxespad=0., numpoints=1)
        elif (self._visualisationType == "final"):
            self._initFigure()
            
            finaldata = []
            labels = []
            colors = []
            for state in sorted(self._initialState.keys(), key=str):
                finaldata.append( evo[state][len(evo[state])-1] )
                labels.append(state)
                colors.append(self._colors[state])
             
#             plt.pie(finaldata, labels=labels, autopct=_make_autopct(piedata), colors=colors) #shadow=True, startangle=90,
            xpos = np.arange(len( self._initialState.keys() ))  # the x locations for the bars
            width = 1       # the width of the bars
            plt.bar(xpos, finaldata, width, color=colors) #, yerr=stdev)
            plt.axes().set_xticks(xpos + width / 2)
            plt.axes().set_xticklabels(sorted(self._initialState.keys(), key=str))

        # update the figure
        if not self._silent:
            self._figure.canvas.draw()
    
    def _singleRun(self, randomSeed):
        # set random seed
        np.random.seed(randomSeed)
        
        # init the controller variables
        self._initMultiagent()
        
        # Create logging structs
        historyState = []
        evo = {}
        evo['time'] = [0]
        for state,pop in self._initialState.items():
            evo[state] = []
            evo[state].append(pop)
         
        t = 0
        currentState = []
        for reactant in sorted(self._mumotModel._reactants, key=str):
            currentState.append(self._initialState[reactant])
        historyState.append( [t] + currentState )
 
        for t in np.arange(1, self._maxTime+1):
            newState = self._stepMultiagent()
            currentState = []
            for reactant in sorted(self._mumotModel._reactants, key=str):
                currentState.append(newState[reactant])

            # log step
            historyState.append( [t] + currentState )
            for state,pop in zip(sorted(self._mumotModel._reactants, key=str), currentState):
                evo[state].append(pop)
            evo['time'].append(t)
                      
#         print("State distribution each timestep: " + str(historyState))
#         print("Temporal evolution per state: " + str(evo))
        return (historyState,evo) 
    
    def _convertRatesIntoProbabilities(self, reactants, rules):
        self._initProbabilitiesMap(reactants, rules)
        #print(self._probabilities)
        self._computeScalingFactor()
        self._applyScalingFactor()
        #print(self._probabilities)
    
    ## derive the transition probabilities map from reaction rules
    def _initProbabilitiesMap(self, reactants, rules):
        self._probabilities = {}
        assignedDestReactants = {}
        for reactant in reactants:
            probSets = {}
            probSets['void'] = []
            for rule in rules:
                if not len(rule.lhsReactants) == len(rule.rhsReactants):
                    print('Raction with varying number of reactacts is not currently supported in multiagent/SSA simulations.' +
                          ' Please, keep the same number of reactants on the left and right handside of each reaction rule.')
                    return 1
                for react in rule.lhsReactants:
                    if react == reactant:
                        numReagents = len(rule.lhsReactants)
                        # if individual transition (i.e. no interaction needed)
                        if numReagents == 1:
                            probSets['void'].append( [rule.rate, self._ratesDict[str(rule.rate)], rule.rhsReactants[0]] )
                        
                        # if interaction transition
                        elif numReagents == 2:
                            # checking if the considered reactant is active or passive in the interaction (i.e. change state afterwards)
                            if reactant not in rule.rhsReactants: # add entry only if the reactant is passive (i.e. change state afterwards)
                                # determining the otherReactant, which is NOT the considered one
                                if rule.lhsReactants[0] == reactant:
                                    otherReact = rule.lhsReactants[1]
                                else:
                                    otherReact = rule.lhsReactants[0]
                                # determining the destReactant
                                if rule.rhsReactants[0] in assignedDestReactants.get(rule, []) or rule.rhsReactants[0] == otherReact :
                                    destReact = rule.rhsReactants[1]
                                else:
                                    destReact = rule.rhsReactants[0]
                                # this is necessary to keep track of the assigned reactant when both reactants change on the right-handside
                                if assignedDestReactants.get(rule) == None:
                                    assignedDestReactants[rule] = []
                                assignedDestReactants[rule].append(destReact)
                                
                                if probSets.get(otherReact) == None:
                                    probSets[otherReact] = []
                                    
                                probSets[otherReact].append( [rule.rate, self._ratesDict[str(rule.rate)], destReact] )
                            else:
                                if rule.lhsReactants.count(reactant) == 2: 
                                    ## @todo: treat in a special way the 'self' interaction!
                                    warningMsg = "WARNING!! Reactant " + str(reactant) + " has a self-reaction " + str(rule.rate) + " which is not currently properly handled."
                                    self._showErrorMessage(warningMsg + "<br>")
                                    
                                    print(warningMsg)
                            
                        elif numReagents > 2:
                            print('More than two reagents in one rule. Unhandled situation, please use at max two reagents per reaction rule')
                            return 1
                        
            self._probabilities[reactant] = probSets
            print("React " + str(reactant))
            print(probSets)

    def _computeScalingFactor(self):
        # Determining the minimum speed of the process (thus the max-scaling factor)
        maxRatesAll = 0
        for probSets in self._probabilities.values():
            voidRates = 0
            maxRates = 0
            for react, probSet in probSets.items():
                tmpRates = 0
                for prob in probSet:
                    #print("adding P=" + str(prob[1]))
                    if react == 'void':
                        voidRates += prob[1]
                    else:
                        tmpRates += prob[1]
                if tmpRates > maxRates:
                    maxRates = tmpRates
            #print("max Rates=" + str(maxRates) + " void Rates=" + str(voidRates))
            if (maxRates + voidRates) > maxRatesAll:
                maxRatesAll = maxRates + voidRates
        #self._scaling = 1/maxRatesAll
        if maxRatesAll>0: self._timestepSize = 1/maxRatesAll 
        else: self._timestepSize = 1
        if self._controller != None: self._update_timestepSize_widget(self._timestepSize)
        print("timestepSize s=" + str(self._timestepSize))
    
    def _update_timestepSize_widget(self, timestepSize):
        if (self._controller._widgetsExtraParams['timestepSize'].value > timestepSize):
            self._controller._widgetsExtraParams['timestepSize'].value = timestepSize  
        if (self._controller._widgetsExtraParams['timestepSize'].max > timestepSize):
            self._controller._widgetsExtraParams['timestepSize'].max = timestepSize
            self._controller._widgetsExtraParams['timestepSize'].min = timestepSize/100
            self._controller._widgetsExtraParams['timestepSize'].step = timestepSize/100 
    
    def _applyScalingFactor(self):
        # Multiply all rates by the scaling factor timestepSize
        for probSets in self._probabilities.values():
            for probSet in probSets.values():
                for prob in probSet:
                    prob[1] *= self._timestepSize
                    
    def _initGraph(self, graphType, numNodes, netParam=None):
        if (graphType == NetworkType.FULLY_CONNECTED):
            print("Generating full graph")
            self._graph = nx.complete_graph(numNodes) #np.repeat(0, self.numNodes)
        elif (graphType == NetworkType.ERSOS_RENYI):
            print("Generating Erdos-Renyi graph (connected)")
            if netParam is not None and netParam > 0 and netParam <= 1: 
                self._graph = nx.erdos_renyi_graph(numNodes, netParam, np.random.randint(MAX_RANDOM_SEED))
                i = 0
                while ( not nx.is_connected( self._graph ) ):
                    print("Graph was not connected; Resampling!")
                    i = i+1
                    self._graph = nx.erdos_renyi_graph(numNodes, netParam, np.random.randint(MAX_RANDOM_SEED)*i*2211)
            else:
                print ("ERROR! Invalid network parameter (link probability) for E-R networks. It must be between 0 and 1; input is " + str(netParam) )
                return
        elif (graphType == NetworkType.BARABASI_ALBERT):
            print("Generating Barabasi-Albert graph")
            netParam = int(netParam)
            if netParam is not None and netParam > 0 and netParam <= numNodes: 
                self._graph = nx.barabasi_albert_graph(numNodes, netParam, np.random.randint(MAX_RANDOM_SEED))
            else:
                print ("ERROR! Invalid network parameter (number of edges per new node) for B-A networks. It must be an integer between 1 and " + str(numNodes) + "; input is " + str(netParam))
                return
        elif (graphType == NetworkType.SPACE):
            ## @todo: implement network generate by placing points (with local communication range) randomly in 2D space
            print("ERROR: Graphs of type SPACE are not implemented yet.")
            return
        elif (graphType == NetworkType.DYNAMIC):
            self._positions = []
            for _ in range(numNodes):
                x = np.random.rand()
                y = np.random.rand()
                o = np.random.rand() * np.pi * 2.0
                self._positions.append( (x,y,o) )
            return

    def _initMultiagent(self):
        # init the agents list
        self._agents = []
        for state, pop in self._initialState.items():
            self._agents.extend( [state]*pop )
        self._agents = np.random.permutation(self._agents).tolist() # random shuffling of elements (useful to avoid initial clusters in networks)
            
        
    def _stepMultiagent(self):
        currentState = {}
        for state in self._initialState.keys():
            currentState[state] = 0
        tmp_agents = copy.deepcopy(self._agents)
        dynamic = self._netType == NetworkType.DYNAMIC
        if dynamic:
            tmp_positions = copy.deepcopy(self._positions)
            communication_range = self._netParam
        for idx, a in enumerate(self._agents):
            if dynamic:
                neighNodes = self._getNeighbours(idx, tmp_positions, communication_range)
#                 print("Agent " + str(idx) + " moved from " + str(self._positions[idx]) )
                self._positions[idx] = self._updatePosition( self._positions[idx][0], self._positions[idx][1], self._positions[idx][2], self._particleSpeed, self._motionCorrelatedness)
#                 print("to position " + str(self._positions[idx]) )
            else:
                neighNodes = list(nx.all_neighbors(self._graph, idx))
            neighAgents = [tmp_agents[x] for x in neighNodes]
#                 print("Neighs of agent " + str(idx) + " are " + str(neighNodes) + " with states " + str(neighAgents) )
            self._agents[idx] = self._stepOneAgent(a, neighAgents)
            currentState[ self._agents[idx] ] = currentState.get(self._agents[idx],0) + 1
        
        return currentState

    ## one timestep for one agent
    def _stepOneAgent(self, agent, neighs):
        #probSets = copy.deepcopy(self._probabilities[agent])
        rnd = np.random.rand()
        lastVal = 0
        probSets = self._probabilities[agent]
        # counting how many neighbours for each state (to be uses for the interaction probabilities)
        neighCount = {x:neighs.count(x) for x in probSets.keys()}
#         print("Agent " + str(agent) + " with probSet=" + str(probSets))
#         print("nc:"+str(neighCount))
        for react, probSet in probSets.items():
            for prob in probSet:
                if react == 'void':
                    popScaling = 1
                else:
                    popScaling = neighCount[react]/len(neighs) if len(neighs) > 0 else 0
                val = popScaling * prob[1]
                if (rnd < val + lastVal):
                    # A state change happened!
                    #print("Reaction: " + str(prob[0]) + " by agent " + str(agent) + " that becomes " + str(prob[2]) )
                    return prob[2]
                else:
                    lastVal += val
        # No state change happened
        return agent
    
    def _updatePosition(self, x, y, o, speed, correlatedness):
        # random component
        rand_o = np.random.rand() * np.pi * 2.0
        rand_x = speed * np.cos(rand_o) * (1-correlatedness)
        rand_y = speed * np.sin(rand_o) * (1-correlatedness)
        # persistance component 
        corr_x = speed * np.cos(o) * correlatedness
        corr_y = speed * np.sin(o) * correlatedness
        # movement
        move_x = rand_x + corr_x
        move_y = rand_y + corr_y
        # new orientation
        o = np.arctan2(move_y, move_x)
        # new position
        x = x + move_x
        y = y + move_y
        
        # Implement the periodic boundary conditions
        x = x % self._arena_width
        y = y % self._arena_height
        #### CODE FOR A BOUNDED ARENA
        # if a.position.x < 0: a.position.x = 0
        # elif a.position.x > self.dimensions.x: a.position.x = self.dimensions.x 
        # if a.position.y < 0: a.position.y = 0
        # elif a.position.y > self.dimensions.y: a.position.x = self.dimensions.x 
        return (x,y,o)

    ## return the (index) list of neighbours of 'agent'
    def _getNeighbours(self, agent, positions, distance_range):
        neighbour_list = []
        for neigh in np.arange(len(positions)):
            if (not neigh == agent) and (self._distance_on_torus(positions[agent][0], positions[agent][1], positions[neigh][0], positions[neigh][1]) < distance_range):
                neighbour_list.append(neigh)
        return neighbour_list
    
    ## returns the minimum distance calucalted on the torus given by periodic boundary conditions
    def _distance_on_torus( self, x_1, y_1, x_2, y_2 ):
        return np.sqrt(min(abs(x_1 - x_2), self._arena_width - abs(x_1 - x_2))**2 + 
                    min(abs(y_1 - y_2), self._arena_height - abs(y_1 - y_2))**2)
    

## agent on networks view on model 
class MuMoTSSAView(MuMoTview): 
    _colors = None
    ## a matrix form of the left-handside of the rules
    _reactantsMatrix = None 
    ## the effect of each rule
    _ruleChanges = None
    ## the system state at the start of the simulation (timestep zero)
    _initialState = None
    ## dictionary of rates
    _ratesDict = None
    ## number of simulation timesteps
    _maxTime = None
    ## random seed
    _randomSeed = None
    ## visualisation type
    _visualisationType = None
    ## realtimePlot flag (TRUE = the plot is updated each timestep of the simulation; FALSE = it is updated once at the end of the simulation)
    _realtimePlot = None
    ## latest computed results
    _latestResults = None

    def __init__(self, model, controller, ssaParams, figure = None, rates = None, **kwargs):
        super().__init__(model, controller, figure=figure, params=rates, **kwargs)

        with io.capture_output() as log:
#         if True:
            if self._controller == None:
                # storing the rates for each rule
                ## @todo moving it to general method?
                self._ratesDict = {}
                rates_input_dict = dict( rates )
#                 print("DIct is " + str(rates_input_dict) )
                for key in rates_input_dict.keys():
                    rates_input_dict[str(process_sympy(str(key)))] = rates_input_dict.pop(key) # replace the dictionary key with the str of the SymPy symbol
                #print("DIct is " + str(rates_input_dict) )
                #print("_mumotModel._rules is " + str(self._mumotModel._rules) )
                # create the self._ratesDict
                for rule in self._mumotModel._rules:
                    self._ratesDict[str(rule.rate)] = rates_input_dict[str(rule.rate)] 
                     
                
            self._initialState = {}
            for state,pop in ssaParams["initialState"].items():
                self._initialState[process_sympy(str(state))] = pop # convert string into SymPy symbol
                #self._initialState[state] = pop
            self._maxTime = ssaParams["maxTime"]
            self._randomSeed = ssaParams["randomSeed"]
            self._visualisationType = ssaParams["visualisationType"]
            self._realtimePlot = ssaParams.get('realtimePlot', False)
            
            # map colouts to each reactant
            #colors = cm.rainbow(np.linspace(0, 1, len(self._mumotModel._reactants) ))  # @UndefinedVariable
            self._colors = {}
            i = 0
            for state in sorted(self._initialState.keys(), key=str): #sorted(self._mumotModel._reactants, key=str):
                self._colors[state] = line_color_list[i] 
                i += 1 
        
        self._logs.append(log)
        if not self._silent:
            self._plot_timeEvolution()

    def _update_params(self):
        if self._controller != None:
            # getting the rates
            ## @todo moving it to general method?
            self._ratesDict = {}
            for rule in self._mumotModel._rules:
                self._ratesDict[str(rule.rate)] = self._controller._widgetsFreeParams[str(rule.rate)].value
            # getting other parameters specific to SSA
            for state in self._initialState.keys():
                self._initialState[state] = self._controller._widgetsExtraParams['init'+str(state)].value
            self._randomSeed = self._controller._widgetsExtraParams['randomSeed'].value
            self._visualisationType = self._controller._widgetsPlotOnly['visualisationType'].value
            self._maxTime = self._controller._widgetsExtraParams['maxTime'].value
            self._realtimePlot = self._controller._widgetsExtraParams['realtimePlot'].value
    
    def _print_standalone_view_cmd(self):
        ssaParams = {}
        initState_str = {}
        for state,pop in self._initialState.items():
            initState_str[str(state)] = pop
        ssaParams["initialState"] = initState_str 
        ssaParams["maxTime"] = self._maxTime 
        ssaParams["randomSeed"] = self._randomSeed
        ssaParams["visualisationType"] = self._visualisationType
        print( "mmt.MuMoTSSAView(model1, None, ssaParams = " + str(ssaParams) + ", rates = " + str( list(self._ratesDict.items()) ) + " )")
    
    def _redrawOnly(self):
        self._update_params()
        self._initFigure()
        self._updateSSAFigure(self._latestResults, fullPlot=True)
    
    def _plot_timeEvolution(self):
        with io.capture_output() as log:
#         if True:
            self._update_params()
            self._log("Stochastic Simulation Algorithm (SSA)")
            self._print_standalone_view_cmd()

            # inti the random seed
            np.random.seed(self._randomSeed)
            
            # organise rates and reactants into strunctures to run the SSA
            #print("Reactants are " + str(sorted(self._mumotModel._reactants, key=str)))
            #print("Const Reactants are " + str(sorted(self._mumotModel._constantReactants, key=str)))
            #self._createSSAmatrix()
            
            # Clearing the plot and setting the axes
            self._initFigure()
           
            self._latestResults = self._runSSA()
            
            ## Final Plot
            if not self._realtimePlot:
                self._updateSSAFigure(self._latestResults, fullPlot=True)
           
        self._logs.append(log)
        
    def _runSSA(self): 
        # Create logging structs
#         historyState = []
        evo = {}
        evo['time'] = [0]
        for state,pop in self._initialState.items():
            evo[state] = []
            evo[state].append(pop)
         
        ## @todo move the progress bar in the view
        if self._controller != None: self._controller._progressBar.max = self._maxTime 
         
        t = 0
#         currentState = []
#         for reactant in sorted(self._mumotModel._reactants|self._mumotModel._constantReactants, key=str):
#             currentState.append(initialState[reactant])
#         historyState.append( [t] + currentState )
        currentState = copy.deepcopy(self._initialState)
 
        while t < self._maxTime:
            # update progress bar
            if self._controller != None: self._controller._progressBar.value = t
            if self._controller != None: self._controller._progressBar.description = "Loading " + str(round(t/self._maxTime*100)) + "%:"
#             print("Time: " + str(t))
             
            timeInterval,currentState = self._stepSSA(currentState)
            if timeInterval == math.inf: timeInterval = self._maxTime-t
            # increment time
            t += timeInterval
             
            # log step
#             historyState.append( [t] + currentState )
#             for state,pop in zip(sorted(self._mumotModel._reactants|self._mumotModel._constantReactants, key=str), currentState):
            for state,pop in currentState.items():
                evo[state].append(pop)
            evo['time'].append(t)
            
#             print (evo)
            ## Plotting each timestep
            if self._realtimePlot:
                self._updateSSAFigure(evo, fullPlot=False)
         
        if self._controller != None: self._controller._progressBar.value = self._controller._progressBar.max
        if self._controller != None: self._controller._progressBar.description = "Completed 100%:"
#         print("State distribution each timestep: " + str(historyState))
#         print("Temporal evolution per state: " + str(evo))
        return evo
    
    def _initFigure(self):
        if not self._silent:
            plt.figure(self._figureNum)
            # Clearing the plot
            plt.clf()

        # Setting the axes
        if (self._visualisationType == 'evo'):
            plt.axes().set_aspect('auto')
            # create the frame
            totAgents = sum(self._initialState.values())
#                     self._plot.axis([0, self._maxTime, 0, totAgents])
            plt.xlim((0, self._maxTime))
            plt.ylim((0, totAgents))
#                 # make legend
#                 markers = [plt.Line2D([0,0],[0,0],color=color, marker='', linestyle='-') for color in self._colors.values()]
#                 self._plot.legend(markers, self._colors.keys(), bbox_to_anchor=(0.85, 0.95), loc=2, borderaxespad=0.)
            #if not self._silent: _fig_formatting_2D(self._figure, xlab="Time", ylab="Reactants", curve_replot=True)
            _fig_formatting_2D(self._figure, xlab="Time", ylab="Reactants", curve_replot=(not self._silent))
            #self._figure.show()
        elif (self._visualisationType == "final"):
#             plt.axes().set_aspect('equal') #for piechart
            plt.axes().set_aspect('auto') # for barchart
            plt.ylim((0, sum(self._initialState.values())))
    
    def _updateSSAFigure(self, evo, fullPlot=True):
        if (self._visualisationType == "evo"):
            if not fullPlot and len(evo['time']) <= 2: # if incremental plot is requested, but it's the first item, we operate as fullPlot (to allow legend)
                fullPlot = True
            # (if fullPlot) plot all time-evolution
            if fullPlot:
                xdata = []
                ydata = []
                labels = []
                for state in sorted(self._initialState.keys(), key=str):
                    if (state == 'time'): continue
                    xdata.append( evo['time'] )
                    ydata.append(evo[state])
                    labels.append(state)
                #xdata=[list(np.arange(len(list(evo.values())[0])))]*len(evo.values()), ydata=list(evo.values()), curvelab=list(evo.keys())
                    #plt.plot(evo['time'], evo[state], color=self._colors[state]) #label=state,
                _fig_formatting_2D(xdata=xdata, ydata=ydata, curvelab=labels, curve_replot=False)
            else: # If realtime-plot mode, draw only the last timestep rather than overlay all
                xdata = []
                ydata = []
                for state in sorted(self._initialState.keys(), key=str):
                    if (state == 'time'): continue
                    xdata.append( evo['time'] )
                    ydata.append( evo[state] )
                    ## @todo replot only the last part (rather than all the line)
#                     xdata.append( [i-1,i] )
#                     pop = evo[state]
#                     ydata.append( pop[len(pop)-2:len(pop)] )
                _fig_formatting_2D(xdata=xdata, ydata=ydata, curve_replot=False)
#                 plt.plot(evo['time'][len(pop)-2:len(pop)], pop[len(pop)-2:len(pop)], color=self._colors[state]) #label=state,
        elif (self._visualisationType == "final"):
            self._initFigure()

            finaldata = []
            labels = []
            colors = []
            for state in sorted(self._initialState.keys(), key=str):
                if (state == 'time'): continue
                finaldata.append( evo[state][len(evo[state])-1] )
                labels.append(state)
                colors.append(self._colors[state])
#             
#             plt.pie(finaldata, labels=labels, autopct=_make_autopct(piedata), colors=colors) #shadow=True, startangle=90,
            xpos = np.arange(len( self._initialState.keys() ))  # the x locations for the bars
            width = 1       # the width of the bars
            
            plt.bar(xpos, finaldata, width, color=colors) #, yerr=stdev)
            plt.axes().set_xticks(xpos + width / 2)
            plt.axes().set_xticklabels(sorted(self._initialState.keys(), key=str))
        
        # update the figure
        if not self._silent:
            self._figure.canvas.draw()
        
    ## @todo Deprecated method to be removed    
    def _createSSAmatrix(self):
        self._reactantsMatrix = [] # list of list: for each rule, there is a (sorted) list containing the rate value multiplied with the number of occurencies for each reactant
        self._ruleChanges = [] # list of list: for each rule, there is a (sorted) list containing the change (e.g., +1, -1, 0) for each reactant 
        for rule in self._mumotModel._rules:
            print("rule: " + str(rule.rate))
            lineR = []
            lineC = []
            for reactant in sorted(self._mumotModel._reactants|self._mumotModel._constantReactants, key=str):
                before = rule.lhsReactants.count(reactant)
                after = rule.rhsReactants.count(reactant)
                lineR.append( before * self._ratesDict[str(rule.rate)] )
                if reactant in self._mumotModel._constantReactants:
                    lineC.append( 0 )
                else:
                    lineC.append( after - before )
            self._reactantsMatrix.append(lineR)
            self._ruleChanges.append(lineC)  
            
    def _stepSSA(self, currentState): 
        # update transition probabilities accounting for the current state
        probabilitiesOfChange = {}
        for reaction_id, reaction in self._mumotModel._stoichiometry.items():
            prob = self._ratesDict[str(reaction["rate"])]
            numReagents = 0  
            for reactant, re_stoch in reaction.items():
                if reactant == 'rate': continue
                if re_stoch == 'const':
                    reactantOccurencies = 1
                else:
                    reactantOccurencies = re_stoch[0]
                if reactantOccurencies > 0:
                    prob *= currentState[reactant] * reactantOccurencies
                numReagents += reactantOccurencies
            if prob > 0 and numReagents > 1:
                prob /= sum(currentState.values())**( numReagents -1 ) 
            probabilitiesOfChange[reaction_id] = prob
#         for rule in self._reactantsMatrix:
#             prob = sum([a*b for a,b in zip(rule,currentState)])
#             numReagents = sum(x > 0 for x in rule)
#             if numReagents > 1:
#                 prob /= sum(currentState)**( numReagents -1 ) 
#             probabilitiesOfChange.append(prob)
        probSum = sum(probabilitiesOfChange.values())
        if probSum == 0: # no reaction are possible (the execution terminates with this population)
            return (math.inf, currentState)
        # computing when is happening next reaction
        timeInterval = np.random.exponential( 1/probSum );
        
        # Selecting the occurred reaction at random, with probability proportional to each reaction probabilities
        bottom = 0.0
        # Get a random between [0,1) (but we don't want 0!)
        reaction = 0.0
        while (reaction == 0.0):
            reaction = np.random.random_sample()
        # Normalising probOfChange in the range [0,1]
#         probabilitiesOfChange = [pc/probSum for pc in probabilitiesOfChange]
        probabilitiesOfChange = {r_id: pc/probSum for r_id, pc in probabilitiesOfChange.items()}
#         print("Prob of Change: " + str(probabilitiesOfChange))
#         index = -1
#         for i, prob in enumerate(probabilitiesOfChange):
#             if ( reaction >= bottom and reaction < (bottom + prob)):
#                 index = i
#                 break
#             bottom += prob
#         
#         if (index == -1):
#             print("ERROR! Transition not found. Error in the algorithm execution.")
#             sys.exit()
        reaction_id = -1
        for r_id, prob in probabilitiesOfChange.items():
            if reaction >= bottom and reaction < (bottom + prob):
                reaction_id = r_id
                break
            bottom += prob
        
        if (reaction_id == -1):
            print("ERROR! Transition not found. Error in the algorithm execution.")
            sys.exit()
#         print("current state: " + str(currentState))
#         print("triggered change: " + str(self._mumotModel._stoichiometry[reaction_id]))
        # apply the change
#         currentState = list(np.array(currentState) + np.array(self._ruleChanges[index]) )
        for reactant, re_stoch in self._mumotModel._stoichiometry[reaction_id].items():
            if reactant == 'rate' or re_stoch == 'const': continue
            currentState[reactant] += re_stoch[1] - re_stoch[0]
            if (currentState[reactant] < 0):
                print("ERROR! Population size became negative: " + str(currentState) + "; Error in the algorithm execution.")
                sys.exit()
        #print(currentState)
                
        return (timeInterval, currentState)
    
    ## @todo check if it is still running correctly after structural change for View independence from Controller (especially, if initialState is correctly initialised)
    def _singleRun(self, randomSeed):
        # set random seed
        np.random.seed(randomSeed)
        # Create logging structs
        historyState = []
        evo = {}
        evo['time'] = [0]
        for state,pop in self._initialState.items():
            evo[state] = []
            evo[state].append(pop)
         
        t = 0
        currentState = []
        for reactant in sorted(self._mumotModel._reactants|self._mumotModel._constantReactants, key=str):
            currentState.append(self._initialState[reactant])
        historyState.append( [t] + currentState )
 
        while t < self._maxTime:
            timeInterval,currentState = self._stepSSA(currentState)
            # increment time
            t += timeInterval

            # log step
            historyState.append( [t] + currentState )
            for state,pop in zip(sorted(self._mumotModel._reactants|self._mumotModel._constantReactants, key=str), currentState):
                evo[state].append(pop)
            evo['time'].append(t)
                      
#         print("State distribution each timestep: " + str(historyState))
#         print("Temporal evolution per state: " + str(evo))
        return (historyState,evo)
    

## create model from text description
def parseModel(modelDescription):
    ## @todo: add system size to model description
    if "get_ipython" in modelDescription:
        # hack to extract model description from input cell tagged with %%model magic
        modelDescr = modelDescription.split("\"")[0].split("'")[5]
    elif "->" in modelDescription:
        # model description provided as string
        modelDescr = modelDescription
    else:
        # assume input describes filename and attempt to load
        assert false
    
    # strip out any basic LaTeX equation formatting user has input
    modelDescr = modelDescr.replace('$','')
    modelDescr = modelDescr.replace(r'\\\\','')
    # split _rules line-by-line, one rule per line
    modelRules = modelDescr.split('\\n')
    # parse and construct the model
    reactants = set()
    constantReactants = set()
    rates = set()
    rules = []
    model = MuMoTmodel()
    
    for rule in modelRules:
        if (len(rule) > 0):
            tokens = rule.split()
            reactantCount = 0
            rate = ""
            state = 'A'
            newRule = _Rule()
            for token in tokens:
                # simulate a simple pushdown automaton to recognise valid _rules, storing representation during processing
                # state A: expecting a reactant (transition to state B)
                # state B: expecting a '+' (transition to state A) or a '->' (transition to state C) (increment reactant count on entering)
                # state C: expecting a reactant (transition to state D)
                # state D: expecting a '+' or a ':' (decrement reactant count on entering)
                # state E: expecting a rate equation until end of rule
                token = token.replace("\\\\",'\\')
                constantReactant = False

                if state == 'A':
                    if token != "+" and token != "->" and token != ":":
                        state = 'B'
                        if '^' in token:
                            raise SyntaxError("Reactants cannot contain '^' :" + token + " in " + rule)
                        reactantCount += 1
                        if (token[0] == '(' and token[-1] == ')'):
                            constantReactant = True
                            token = token.replace('(','')
                            token = token.replace(')','')
                        if token == '\emptyset':
                            constantReactant = True
                            model._constantSystemSize = False
                            token = '1'
                        expr = process_sympy(token)
                        reactantAtoms = expr.atoms()
                        if len(reactantAtoms) != 1:
                            raise SyntaxError("Non-singleton symbol set in token " + token +" in rule " + rule)
                        for reactant in reactantAtoms:
                            pass # this loop extracts element from singleton set
                        if constantReactant:
                            if reactant not in constantReactants and token != '1':
                                constantReactants.add(reactant)                            
                        else:
                            if reactant not in reactants:
                                reactants.add(reactant)
                        newRule.lhsReactants.append(reactant)
                    else:
                        _raiseModelError("reactant", token, rule)
                        return
                elif state == 'B':
                    if token == "->":
                        state = 'C'
                    elif token == '+':
                        state = 'A'
                    else:
                        _raiseModelError("'->' or '+'", token, rule)
                        return
                elif state == 'C':
                    if token != "+" and token != "->" and token != ":":
                        state = 'D'
                        if '^' in token:
                            raise SyntaxError("Reactants cannot contain '^' :" + token + " in " + rule)
                        reactantCount -= 1
                        if (token[0] == '(' and token[-1] == ')'):
                            constantReactant = True
                            token = token.replace('(','')
                            token = token.replace(')','')
                        if token == '\emptyset':
                            model._constantSystemSize = False
                            constantReactant = True
                            token = '1'
                        expr = process_sympy(token)
                        reactantAtoms = expr.atoms()
                        if len(reactantAtoms) != 1:
                            raise SyntaxError("Non-singleton symbol set in token " + token +" in rule " + rule)
                        for reactant in reactantAtoms:
                            pass # this loop extracts element from singleton set
                        if constantReactant:
                            if reactant not in constantReactants and token != '1':
                                constantReactants.add(reactant)                            
                        else:
                            if reactant not in reactants:
                                reactants.add(reactant)
                        newRule.rhsReactants.append(reactant)                        
                    else:
                        _raiseModelError("reactant", token, rule)
                        return
                elif state == 'D':
                    if token == ":":
                        state = 'E'
                    elif token == '+':
                        state = 'C'
                    else:
                        _raiseModelError("':' or '+'", token, rule)
                        return
                elif state == 'E':
                    rate += token
                    # state = 'F'
                else:
                    # should never reach here
                    assert False

            newRule.rate = process_sympy(rate) 
            rateAtoms = newRule.rate.atoms(Symbol)
            for atom in rateAtoms:
                if atom not in rates:
                    rates.add(atom)
                    
            if reactantCount == 0:
                rules.append(newRule)
            else:
                raise SyntaxError("Unequal number of reactants on lhs and rhs of rule " + rule)

            
    model._rules = rules
    model._reactants = reactants
    model._constantReactants = constantReactants
    # check intersection of reactants and constantReactants is empty
    intersect = model._reactants.intersection(model._constantReactants) 
    if len(intersect) != 0:
        raise SyntaxError("Following reactants defined as both constant and variable: " + str(intersect))
    model._rates = rates
    model._equations = _deriveODEsFromRules(model._reactants, model._rules)
    model._ratesLaTeX = {}
    rates = map(latex, list(model._rates))
    for (rate, latexStr) in zip(model._rates, rates):
        model._ratesLaTeX[repr(rate)] = latexStr
    constantReactants = map(latex, list(model._constantReactants))
    for (reactant, latexStr) in zip(model._constantReactants, constantReactants):
        model._ratesLaTeX[repr(reactant)] = '(' + latexStr + ')'    
    
    model._stoichiometry = _getStoichiometry(model._rules, model._constantReactants)
    
    return model

def _deriveODEsFromRules(reactants, rules):
    ## @todo: replace with principled derivation via Master Equation and van Kampen expansion
    equations = {}
    terms = []
    for rule in rules:
        term = None
        for reactant in rule.lhsReactants:
            if term == None:
                term = reactant
            else:
                term = term * reactant
        term = term * rule.rate
        terms.append(term)
    for reactant in reactants:
        rhs = None       
        for rule, term in zip(rules, terms):
            # I love Python!
            factor = rule.rhsReactants.count(reactant) - rule.lhsReactants.count(reactant)
            if factor != 0:
                if rhs == None:
                    rhs = factor * term
                else:
                    rhs = rhs + factor * term
        equations[reactant] = rhs
    

    return equations

## produces dictionary with stoichiometry of all reactions with key ReactionNr
# ReactionNr represents another dictionary with reaction rate, reactants and their stoichiometry
def _getStoichiometry(rules, const_reactants):
    stoich = {}
    ReactionNr = numbered_symbols(prefix='Reaction ', cls=Symbol, start=1)
    for rule in rules:
        reactDict = {'rate': rule.rate}
        for reactant in rule.lhsReactants:
            if reactant != 1:
                if reactant in const_reactants:
                    reactDict[reactant] = 'const'
                else:
                    reactDict[reactant] = [rule.lhsReactants.count(reactant), rule.rhsReactants.count(reactant)]
        for reactant in rule.rhsReactants:
            if reactant != 1:
                if reactant not in rule.lhsReactants:
                    if reactant not in const_reactants:
                        reactDict[reactant] = [rule.lhsReactants.count(reactant), rule.rhsReactants.count(reactant)]
        stoich[ReactionNr.__next__()] = reactDict
        
    return stoich


## derivation of the Master equation, returns dictionary used in showMasterEquation
def _deriveMasterEquation(stoichiometry):
    substring = None
    P, E_op, x, y, v, w, t, m = symbols('P E_op x y v w t m')
    V = Symbol('V', real=True, constant=True)
    stoich = stoichiometry
    nvec = []
    for key1 in stoich:
        for key2 in stoich[key1]:
            if key2 != 'rate' and stoich[key1][key2] != 'const':
                if not key2 in nvec:
                    nvec.append(key2)
                if len(stoich[key1][key2]) == 3:
                    substring = stoich[key1][key2][2]
    nvec = sorted(nvec, key=default_sort_key)
    
    assert (len(nvec)==2 or len(nvec)==3 or len(nvec)==4), 'This module works for 2, 3 or 4 different reactants only'
    
    rhs = 0
    sol_dict_rhs = {}
    f = lambdify((x(y, v-w)), x(y, v-w), modules='sympy')
    g = lambdify((x, y, v), (factorial(x)/factorial(x-y))/v**y, modules='sympy')
    for key1 in stoich:
        prod1 = 1
        prod2 = 1
        rate_fact = 1
        for key2 in stoich[key1]:
            if key2 != 'rate' and stoich[key1][key2] != 'const':
                prod1 *= f(E_op(key2, stoich[key1][key2][0]-stoich[key1][key2][1]))
                prod2 *= g(key2, stoich[key1][key2][0], V)
            if stoich[key1][key2] == 'const':
                rate_fact *= key2/V
        if len(nvec)==2:
            sol_dict_rhs[key1] = (prod1, simplify(prod2*V), P(nvec[0], nvec[1], t), stoich[key1]['rate']*rate_fact)
        elif len(nvec)==3:
            sol_dict_rhs[key1] = (prod1, simplify(prod2*V), P(nvec[0], nvec[1], nvec[2], t), stoich[key1]['rate']*rate_fact)
        else:
            sol_dict_rhs[key1] = (prod1, simplify(prod2*V), P(nvec[0], nvec[1], nvec[2], nvec[3], t), stoich[key1]['rate']*rate_fact)

    return sol_dict_rhs, substring


## Function returning the left-hand side and right-hand side of van Kampen expansion    
def _doVanKampenExpansion(rhs, stoich):
    P, E_op, x, y, v, w, t, m = symbols('P E_op x y v w t m')
    V = Symbol('V', real=True, constant=True)
    nvec = []
    nconstvec = []
    for key1 in stoich:
        for key2 in stoich[key1]:
            if key2 != 'rate' and stoich[key1][key2] != 'const':
                if not key2 in nvec:
                    nvec.append(key2)
            elif key2 != 'rate' and stoich[key1][key2] == 'const':
                if not key2 in nconstvec:
                    nconstvec.append(key2)
                    
    nvec = sorted(nvec, key=default_sort_key)
    assert (len(nvec)==2 or len(nvec)==3 or len(nvec)==4), 'This module works for 2, 3 or 4 different reactants only'
    
    NoiseDict = {}
    PhiDict = {}
    PhiConstDict = {}
    
    for kk in range(len(nvec)):
        NoiseDict[nvec[kk]] = Symbol('eta_'+str(nvec[kk]))
        PhiDict[nvec[kk]] = Symbol('Phi_'+str(nvec[kk]))
        
    for kk in range(len(nconstvec)):
        PhiConstDict[nconstvec[kk]] = V*Symbol('Phi_'+str(nconstvec[kk]))

        
    rhs_dict, substring = rhs(stoich)
    rhs_vKE = 0
    
    if len(nvec)==2:
        lhs_vKE = (Derivative(P(nvec[0], nvec[1],t),t).subs({nvec[0]: NoiseDict[nvec[0]], nvec[1]: NoiseDict[nvec[1]]})
                  - sqrt(V)*Derivative(PhiDict[nvec[0]],t)*Derivative(P(nvec[0], nvec[1],t),nvec[0]).subs({nvec[0]: NoiseDict[nvec[0]], nvec[1]: NoiseDict[nvec[1]]})
                  - sqrt(V)*Derivative(PhiDict[nvec[1]],t)*Derivative(P(nvec[0], nvec[1],t),nvec[1]).subs({nvec[0]: NoiseDict[nvec[0]], nvec[1]: NoiseDict[nvec[1]]}))

        for key in rhs_dict:
            op = rhs_dict[key][0].subs({nvec[0]: NoiseDict[nvec[0]], nvec[1]: NoiseDict[nvec[1]]})
            func1 = rhs_dict[key][1].subs({nvec[0]: V*PhiDict[nvec[0]]+sqrt(V)*NoiseDict[nvec[0]], nvec[1]: V*PhiDict[nvec[1]]+sqrt(V)*NoiseDict[nvec[1]]})
            func2 = rhs_dict[key][2].subs({nvec[0]: NoiseDict[nvec[0]], nvec[1]: NoiseDict[nvec[1]]})
            func = func1*func2
            if len(op.args[0].args) ==0:
                term = (op*func).subs({op*func: func + op.args[1]/sqrt(V)*Derivative(func, op.args[0]) + op.args[1]**2/(2*V)*Derivative(func, op.args[0], op.args[0]) })
                
            else:
                term = (op.args[1]*func).subs({op.args[1]*func: func + op.args[1].args[1]/sqrt(V)*Derivative(func, op.args[1].args[0]) 
                                       + op.args[1].args[1]**2/(2*V)*Derivative(func, op.args[1].args[0], op.args[1].args[0])})
                term = (op.args[0]*term).subs({op.args[0]*term: term + op.args[0].args[1]/sqrt(V)*Derivative(term, op.args[0].args[0]) 
                                       + op.args[0].args[1]**2/(2*V)*Derivative(term, op.args[0].args[0], op.args[0].args[0])})
            #term_num, term_denom = term.as_numer_denom()
            rhs_vKE += rhs_dict[key][3].subs(PhiConstDict)*(term.doit() - func)
    elif len(nvec)==3:
        lhs_vKE = (Derivative(P(nvec[0], nvec[1], nvec[2], t), t).subs({nvec[0]: NoiseDict[nvec[0]], nvec[1]: NoiseDict[nvec[1]], nvec[2]: NoiseDict[nvec[2]]})
                  - sqrt(V)*Derivative(PhiDict[nvec[0]],t)*Derivative(P(nvec[0], nvec[1], nvec[2], t), nvec[0]).subs({nvec[0]: NoiseDict[nvec[0]], nvec[1]: NoiseDict[nvec[1]], nvec[2]: NoiseDict[nvec[2]]})
                  - sqrt(V)*Derivative(PhiDict[nvec[1]],t)*Derivative(P(nvec[0], nvec[1], nvec[2], t), nvec[1]).subs({nvec[0]: NoiseDict[nvec[0]], nvec[1]: NoiseDict[nvec[1]], nvec[2]: NoiseDict[nvec[2]]})
                  - sqrt(V)*Derivative(PhiDict[nvec[2]],t)*Derivative(P(nvec[0], nvec[1], nvec[2], t), nvec[2]).subs({nvec[0]: NoiseDict[nvec[0]], nvec[1]: NoiseDict[nvec[1]], nvec[2]: NoiseDict[nvec[2]]}))
        rhs_dict, substring = rhs(stoich)
        rhs_vKE = 0
        for key in rhs_dict:
            op = rhs_dict[key][0].subs({nvec[0]: NoiseDict[nvec[0]], nvec[1]: NoiseDict[nvec[1]], nvec[2]: NoiseDict[nvec[2]]})
            func1 = rhs_dict[key][1].subs({nvec[0]: V*PhiDict[nvec[0]]+sqrt(V)*NoiseDict[nvec[0]], nvec[1]: V*PhiDict[nvec[1]]+sqrt(V)*NoiseDict[nvec[1]], nvec[2]: V*PhiDict[nvec[2]]+sqrt(V)*NoiseDict[nvec[2]]})
            func2 = rhs_dict[key][2].subs({nvec[0]: NoiseDict[nvec[0]], nvec[1]: NoiseDict[nvec[1]], nvec[2]: NoiseDict[nvec[2]]})
            func = func1*func2
            if len(op.args[0].args) ==0:
                term = (op*func).subs({op*func: func + op.args[1]/sqrt(V)*Derivative(func, op.args[0]) + op.args[1]**2/(2*V)*Derivative(func, op.args[0], op.args[0]) })
                
            elif len(op.args) ==2:
                term = (op.args[1]*func).subs({op.args[1]*func: func + op.args[1].args[1]/sqrt(V)*Derivative(func, op.args[1].args[0]) 
                                       + op.args[1].args[1]**2/(2*V)*Derivative(func, op.args[1].args[0], op.args[1].args[0])})
                term = (op.args[0]*term).subs({op.args[0]*term: term + op.args[0].args[1]/sqrt(V)*Derivative(term, op.args[0].args[0]) 
                                       + op.args[0].args[1]**2/(2*V)*Derivative(term, op.args[0].args[0], op.args[0].args[0])})
            elif len(op.args) ==3:
                term = (op.args[2]*func).subs({op.args[2]*func: func + op.args[2].args[1]/sqrt(V)*Derivative(func, op.args[2].args[0]) 
                                       + op.args[2].args[1]**2/(2*V)*Derivative(func, op.args[2].args[0], op.args[2].args[0])})
                term = (op.args[1]*term).subs({op.args[1]*term: term + op.args[1].args[1]/sqrt(V)*Derivative(term, op.args[1].args[0]) 
                                       + op.args[1].args[1]**2/(2*V)*Derivative(term, op.args[1].args[0], op.args[1].args[0])})
                term = (op.args[0]*term).subs({op.args[0]*term: term + op.args[0].args[1]/sqrt(V)*Derivative(term, op.args[0].args[0]) 
                                       + op.args[0].args[1]**2/(2*V)*Derivative(term, op.args[0].args[0], op.args[0].args[0])})
            else:
                print('Something went wrong!')
            rhs_vKE += rhs_dict[key][3].subs(PhiConstDict)*(term.doit() - func)    
    else:
        lhs_vKE = (Derivative(P(nvec[0], nvec[1], nvec[2], nvec[3], t), t).subs({nvec[0]: NoiseDict[nvec[0]], nvec[1]: NoiseDict[nvec[1]], nvec[2]: NoiseDict[nvec[2]], nvec[3]: NoiseDict[nvec[3]]})
                  - sqrt(V)*Derivative(PhiDict[nvec[0]],t)*Derivative(P(nvec[0], nvec[1], nvec[2], nvec[3], t), nvec[0]).subs({nvec[0]: NoiseDict[nvec[0]], nvec[1]: NoiseDict[nvec[1]], nvec[2]: NoiseDict[nvec[2]], nvec[3]: NoiseDict[nvec[3]]})
                  - sqrt(V)*Derivative(PhiDict[nvec[1]],t)*Derivative(P(nvec[0], nvec[1], nvec[2], nvec[3], t), nvec[1]).subs({nvec[0]: NoiseDict[nvec[0]], nvec[1]: NoiseDict[nvec[1]], nvec[2]: NoiseDict[nvec[2]], nvec[3]: NoiseDict[nvec[3]]})
                  - sqrt(V)*Derivative(PhiDict[nvec[2]],t)*Derivative(P(nvec[0], nvec[1], nvec[2], nvec[3], t), nvec[2]).subs({nvec[0]: NoiseDict[nvec[0]], nvec[1]: NoiseDict[nvec[1]], nvec[2]: NoiseDict[nvec[2]], nvec[3]: NoiseDict[nvec[3]]})
                  - sqrt(V)*Derivative(PhiDict[nvec[3]],t)*Derivative(P(nvec[0], nvec[1], nvec[2], nvec[3], t), nvec[3]).subs({nvec[0]: NoiseDict[nvec[0]], nvec[1]: NoiseDict[nvec[1]], nvec[2]: NoiseDict[nvec[2]], nvec[3]: NoiseDict[nvec[3]]}))
        rhs_dict, substring = rhs(stoich)
        rhs_vKE = 0
        for key in rhs_dict:
            op = rhs_dict[key][0].subs({nvec[0]: NoiseDict[nvec[0]], nvec[1]: NoiseDict[nvec[1]], nvec[2]: NoiseDict[nvec[2]], nvec[3]: NoiseDict[nvec[3]]})
            func1 = rhs_dict[key][1].subs({nvec[0]: V*PhiDict[nvec[0]]+sqrt(V)*NoiseDict[nvec[0]], nvec[1]: V*PhiDict[nvec[1]]+sqrt(V)*NoiseDict[nvec[1]], nvec[2]: V*PhiDict[nvec[2]]+sqrt(V)*NoiseDict[nvec[2]], nvec[3]: V*PhiDict[nvec[3]]+sqrt(V)*NoiseDict[nvec[3]]})
            func2 = rhs_dict[key][2].subs({nvec[0]: NoiseDict[nvec[0]], nvec[1]: NoiseDict[nvec[1]], nvec[2]: NoiseDict[nvec[2]], nvec[3]: NoiseDict[nvec[3]]})
            func = func1*func2
            if len(op.args[0].args) ==0:
                term = (op*func).subs({op*func: func + op.args[1]/sqrt(V)*Derivative(func, op.args[0]) + op.args[1]**2/(2*V)*Derivative(func, op.args[0], op.args[0]) })
                
            elif len(op.args) ==2:
                term = (op.args[1]*func).subs({op.args[1]*func: func + op.args[1].args[1]/sqrt(V)*Derivative(func, op.args[1].args[0]) 
                                       + op.args[1].args[1]**2/(2*V)*Derivative(func, op.args[1].args[0], op.args[1].args[0])})
                term = (op.args[0]*term).subs({op.args[0]*term: term + op.args[0].args[1]/sqrt(V)*Derivative(term, op.args[0].args[0]) 
                                       + op.args[0].args[1]**2/(2*V)*Derivative(term, op.args[0].args[0], op.args[0].args[0])})
            elif len(op.args) ==3:
                term = (op.args[2]*func).subs({op.args[2]*func: func + op.args[2].args[1]/sqrt(V)*Derivative(func, op.args[2].args[0]) 
                                       + op.args[2].args[1]**2/(2*V)*Derivative(func, op.args[2].args[0], op.args[2].args[0])})
                term = (op.args[1]*term).subs({op.args[1]*term: term + op.args[1].args[1]/sqrt(V)*Derivative(term, op.args[1].args[0]) 
                                       + op.args[1].args[1]**2/(2*V)*Derivative(term, op.args[1].args[0], op.args[1].args[0])})
                term = (op.args[0]*term).subs({op.args[0]*term: term + op.args[0].args[1]/sqrt(V)*Derivative(term, op.args[0].args[0]) 
                                       + op.args[0].args[1]**2/(2*V)*Derivative(term, op.args[0].args[0], op.args[0].args[0])})
            elif len(op.args) ==4:
                term = (op.args[3]*func).subs({op.args[3]*func: func + op.args[3].args[1]/sqrt(V)*Derivative(func, op.args[3].args[0]) 
                                       + op.args[3].args[1]**2/(2*V)*Derivative(func, op.args[3].args[0], op.args[3].args[0])})
                term = (op.args[2]*term).subs({op.args[2]*term: term + op.args[2].args[1]/sqrt(V)*Derivative(term, op.args[2].args[0]) 
                                       + op.args[2].args[1]**2/(2*V)*Derivative(term, op.args[2].args[0], op.args[2].args[0])})
                term = (op.args[1]*term).subs({op.args[1]*term: term + op.args[1].args[1]/sqrt(V)*Derivative(term, op.args[1].args[0]) 
                                       + op.args[1].args[1]**2/(2*V)*Derivative(term, op.args[1].args[0], op.args[1].args[0])})
                term = (op.args[0]*term).subs({op.args[0]*term: term + op.args[0].args[1]/sqrt(V)*Derivative(term, op.args[0].args[0]) 
                                       + op.args[0].args[1]**2/(2*V)*Derivative(term, op.args[0].args[0], op.args[0].args[0])})
            else:
                print('Something went wrong!')
            rhs_vKE += rhs_dict[key][3].subs(PhiConstDict)*(term.doit() - func)
    
    return rhs_vKE.expand(), lhs_vKE, substring

## creates list of dictionaries where the key is the system size order
#def _get_orderedLists_vKE( _getStoichiometry,rules):
def _get_orderedLists_vKE(stoich):
    V = Symbol('V', real=True, constant=True)
    stoichiometry = stoich
    rhs_vke, lhs_vke, substring = _doVanKampenExpansion(_deriveMasterEquation, stoichiometry)
    Vlist_lhs=[]
    Vlist_rhs=[]
    for jj in range(len(rhs_vke.args)):
        try:
            Vlist_rhs.append(simplify(rhs_vke.args[jj]).collect(V, evaluate=False))
        except NotImplementedError:
            prod=1
            for nn in range(len(rhs_vke.args[jj].args)-1):
                prod*=rhs_vke.args[jj].args[nn]
            tempdict=prod.collect(V, evaluate=False)
            for key in tempdict:
                Vlist_rhs.append({key: prod/key*rhs_vke.args[jj].args[-1]})
    
    for jj in range(len(lhs_vke.args)):
        try:
            Vlist_lhs.append(simplify(lhs_vke.args[jj]).collect(V, evaluate=False))
        except NotImplementedError:
            prod=1
            for nn in range(len(lhs_vke.args[jj].args)-1):
                prod*=lhs_vke.args[jj].args[nn]
            tempdict=prod.collect(V, evaluate=False)
            for key in tempdict:
                Vlist_lhs.append({key: prod/key*lhs_vke.args[jj].args[-1]})
    return Vlist_lhs, Vlist_rhs, substring


## Function that returns the Fokker-Planck equation
def _getFokkerPlanckEquation(_get_orderedLists_vKE, stoich):
    P, t = symbols('P t')
    V = Symbol('V', real=True, constant=True)
    Vlist_lhs, Vlist_rhs, substring = _get_orderedLists_vKE(stoich)
    rhsFPE=0
    lhsFPE=0
    for kk in range(len(Vlist_rhs)):
        for key in Vlist_rhs[kk]:
            if key==1:
                rhsFPE += Vlist_rhs[kk][key]  
    for kk in range(len(Vlist_lhs)):
        for key in Vlist_lhs[kk]:
            if key==1:
                lhsFPE += Vlist_lhs[kk][key]            
        
    FPE = lhsFPE-rhsFPE
    
    nvec = []
    for key1 in stoich:
        for key2 in stoich[key1]:
            if key2 != 'rate' and stoich[key1][key2] != 'const':
                if not key2 in nvec:
                    nvec.append(key2)
    nvec = sorted(nvec, key=default_sort_key)
    assert (len(nvec)==2 or len(nvec)==3 or len(nvec)==4), 'This module works for 2, 3 or 4 different reactants only'
    
    NoiseDict = {}
    for kk in range(len(nvec)):
        NoiseDict[nvec[kk]] = Symbol('eta_'+str(nvec[kk]))
    
    if len(Vlist_lhs)-1 == 2:
        SOL_FPE = solve(FPE, Derivative(P(NoiseDict[nvec[0]],NoiseDict[nvec[1]],t),t), dict=True)[0]
    elif len(Vlist_lhs)-1 == 3:
        SOL_FPE = solve(FPE, Derivative(P(NoiseDict[nvec[0]],NoiseDict[nvec[1]],NoiseDict[nvec[2]],t),t), dict=True)[0]
    elif len(Vlist_lhs)-1 == 4:
        SOL_FPE = solve(FPE, Derivative(P(NoiseDict[nvec[0]],NoiseDict[nvec[1]],NoiseDict[nvec[2]],NoiseDict[nvec[3]],t),t), dict=True)[0]
    else:
        print('Not implemented yet.')
           
    return SOL_FPE, substring


## calculates noise in the system
# returns equations of motion for noise
def _getNoiseEOM(_getFokkerPlanckEquation, _get_orderedLists_vKE, stoich):
    P, M_1, M_2, t = symbols('P M_1 M_2 t')
    #
    #A,B, alpha, beta, gamma = symbols('A B alpha beta gamma')
    #custom_stoich= {'reaction1': {'rate': alpha, A: [0,1]}, 'reaction2': {'rate': gamma, A: [2,0], B: [0,1]},
    #                 'reaction3': {'rate': beta, B: [1,0]}}
    #stoich = custom_stoich
    # 
    nvec = []
    for key1 in stoich:
        for key2 in stoich[key1]:
            if key2 != 'rate' and stoich[key1][key2] != 'const':
                if key2 not in nvec:
                    nvec.append(key2)
    nvec = sorted(nvec, key=default_sort_key)
    assert (len(nvec)==2 or len(nvec)==3 or len(nvec)==4), 'This module works for 2, 3 or 4 different reactants only'

    NoiseDict = {}
    for kk in range(len(nvec)):
        NoiseDict[nvec[kk]] = Symbol('eta_'+str(nvec[kk]))
    FPEdict, substring = _getFokkerPlanckEquation(_get_orderedLists_vKE, stoich)
    
    NoiseSub1stOrder = {}
    NoiseSub2ndOrder = {}

    if len(NoiseDict)==2:
        Pdim = P(NoiseDict[nvec[0]],NoiseDict[nvec[1]],t)
    elif len(NoiseDict)==3:
        Pdim = P(NoiseDict[nvec[0]],NoiseDict[nvec[1]],NoiseDict[nvec[2]],t)
    else:
        Pdim = P(NoiseDict[nvec[0]],NoiseDict[nvec[1]],NoiseDict[nvec[2]],NoiseDict[nvec[3]],t)
        
    for noise1 in NoiseDict:
        NoiseSub1stOrder[NoiseDict[noise1]*Pdim] = M_1(NoiseDict[noise1])
        for noise2 in NoiseDict:
            for noise3 in NoiseDict:
                key = NoiseDict[noise1]*NoiseDict[noise2]*Derivative(Pdim,NoiseDict[noise3])
                if key not in NoiseSub1stOrder:
                    if NoiseDict[noise1] == NoiseDict[noise2] and NoiseDict[noise3] == NoiseDict[noise1]:
                        NoiseSub1stOrder[key] = -2*M_1(NoiseDict[noise1])
                    elif NoiseDict[noise1] != NoiseDict[noise2] and NoiseDict[noise3] == NoiseDict[noise1]:
                        NoiseSub1stOrder[key] = -M_1(NoiseDict[noise2])
                    elif NoiseDict[noise1] != NoiseDict[noise2] and NoiseDict[noise3] == NoiseDict[noise2]:
                        NoiseSub1stOrder[key] = -M_1(NoiseDict[noise1])
                    elif NoiseDict[noise1] != NoiseDict[noise3] and NoiseDict[noise3] != NoiseDict[noise2]:
                        NoiseSub1stOrder[key] = 0
                    else:
                        NoiseSub1stOrder[key] = 0 
                key2 = NoiseDict[noise1]*Derivative(Pdim,NoiseDict[noise2],NoiseDict[noise3])
                if key2 not in NoiseSub1stOrder:
                    NoiseSub1stOrder[key2] = 0   
    
    for noise1 in NoiseDict:
        for noise2 in NoiseDict:
            key = NoiseDict[noise1]*NoiseDict[noise2]*Pdim
            if key not in NoiseSub2ndOrder:
                NoiseSub2ndOrder[key] = M_2(NoiseDict[noise1]*NoiseDict[noise2])
            for noise3 in NoiseDict:
                for noise4 in NoiseDict:
                    key2 = NoiseDict[noise1]*NoiseDict[noise2]*NoiseDict[noise3]*Derivative(Pdim,NoiseDict[noise4])
                    if key2 not in NoiseSub2ndOrder:
                        if noise1 == noise2 and noise2 == noise3 and noise3 == noise4:
                            NoiseSub2ndOrder[key2] = -3*M_2(NoiseDict[noise1]*NoiseDict[noise1])
                        elif noise1 == noise2 and noise2 != noise3 and noise1 == noise4:
                            NoiseSub2ndOrder[key2] = -2*M_2(NoiseDict[noise1]*NoiseDict[noise3])
                        elif noise1 == noise2 and noise2 != noise3 and noise3 == noise4:
                            NoiseSub2ndOrder[key2] = -M_2(NoiseDict[noise1]*NoiseDict[noise2])
                        elif noise1 != noise2 and noise2 == noise3 and noise1 == noise4:
                            NoiseSub2ndOrder[key2] = -M_2(NoiseDict[noise2]*NoiseDict[noise3])
                        elif noise1 != noise2 and noise2 == noise3 and noise3 == noise4:
                            NoiseSub2ndOrder[key2] = -2*M_2(NoiseDict[noise1]*NoiseDict[noise2])
                        elif noise1 != noise2 and noise2 != noise3 and noise1 != noise3:
                            if noise1 == noise4:
                                NoiseSub2ndOrder[key2] = -M_2(NoiseDict[noise2]*NoiseDict[noise3])
                            elif noise2 == noise4:
                                NoiseSub2ndOrder[key2] = -M_2(NoiseDict[noise1]*NoiseDict[noise3])
                            elif noise3 == noise4:
                                NoiseSub2ndOrder[key2] = -M_2(NoiseDict[noise1]*NoiseDict[noise2])
                            else:
                                NoiseSub2ndOrder[key2] = 0
                        else:
                            NoiseSub2ndOrder[key2] = 0
                    key3 = NoiseDict[noise1]*NoiseDict[noise2]*Derivative(Pdim,NoiseDict[noise3],NoiseDict[noise4])
                    if key3 not in NoiseSub2ndOrder:
                        if noise1 == noise3 and noise2 == noise4:
                            if noise1 == noise2:
                                NoiseSub2ndOrder[key3] = 2
                            else:
                                 NoiseSub2ndOrder[key3] = 1
                        elif noise1 == noise4 and noise2 == noise3:
                            if noise1 == noise2:
                                NoiseSub2ndOrder[key3] = 2
                            else:
                                NoiseSub2ndOrder[key3] = 1
                        else:
                            NoiseSub2ndOrder[key3] = 0
    NoiseSubs1stOrder = {}                   
    EQsys1stOrdMom = []
    EOM_1stOrderMom = {}
    for fpe_lhs in FPEdict: 
        for noise in NoiseDict:
            eq1stOrderMoment = (NoiseDict[noise]*FPEdict[fpe_lhs]).expand() 
            eq1stOrderMoment = eq1stOrderMoment.subs(NoiseSub1stOrder)
            if len(NoiseDict)==2:
                eq1stOrderMoment = collect(eq1stOrderMoment, M_1(NoiseDict[nvec[0]]))
                eq1stOrderMoment = collect(eq1stOrderMoment, M_1(NoiseDict[nvec[1]]))
            elif len(NoiseDict)==3:
                eq1stOrderMoment = collect(eq1stOrderMoment, M_1(NoiseDict[nvec[0]]))
                eq1stOrderMoment = collect(eq1stOrderMoment, M_1(NoiseDict[nvec[1]]))
                eq1stOrderMoment = collect(eq1stOrderMoment, M_1(NoiseDict[nvec[2]]))
            else:
                eq1stOrderMoment = collect(eq1stOrderMoment, M_1(NoiseDict[nvec[0]]))
                eq1stOrderMoment = collect(eq1stOrderMoment, M_1(NoiseDict[nvec[1]]))
                eq1stOrderMoment = collect(eq1stOrderMoment, M_1(NoiseDict[nvec[2]]))
                eq1stOrderMoment = collect(eq1stOrderMoment, M_1(NoiseDict[nvec[3]]))
            EQsys1stOrdMom.append(eq1stOrderMoment)
            if M_1(NoiseDict[noise]) not in EOM_1stOrderMom:
                EOM_1stOrderMom[M_1(NoiseDict[noise])] = eq1stOrderMoment
                NoiseSubs1stOrder[M_1(NoiseDict[noise])] = r'\left< \vphantom{Dg}\right.' +latex(NoiseDict[noise]) + r'\left. \vphantom{Dg}\right>'
    
    NoiseSubs2ndOrder = {}
    EQsys2ndOrdMom = []
    EOM_2ndOrderMom = {}
    for fpe_lhs in FPEdict: 
        for noise1 in NoiseDict:
            for noise2 in NoiseDict:
                eq2ndOrderMoment = (NoiseDict[noise1]*NoiseDict[noise2]*FPEdict[fpe_lhs]).expand() 
                eq2ndOrderMoment = eq2ndOrderMoment.subs(NoiseSub2ndOrder)
                eq2ndOrderMoment = eq2ndOrderMoment.subs(NoiseSub1stOrder)
                #eq2ndOrderMoment = eq2ndOrderMoment.subs(SOL_1stOrderMom[0])
                if len(NoiseDict)==2:
                    eq2ndOrderMoment = collect(eq2ndOrderMoment, M_2(NoiseDict[nvec[0]]*NoiseDict[nvec[0]]))
                    eq2ndOrderMoment = collect(eq2ndOrderMoment, M_2(NoiseDict[nvec[1]]*NoiseDict[nvec[1]]))
                    eq2ndOrderMoment = collect(eq2ndOrderMoment, M_2(NoiseDict[nvec[0]]*NoiseDict[nvec[1]]))
                elif len(NoiseDict)==3:
                    eq2ndOrderMoment = collect(eq2ndOrderMoment, M_2(NoiseDict[nvec[0]]*NoiseDict[nvec[0]]))
                    eq2ndOrderMoment = collect(eq2ndOrderMoment, M_2(NoiseDict[nvec[1]]*NoiseDict[nvec[1]]))
                    eq2ndOrderMoment = collect(eq2ndOrderMoment, M_2(NoiseDict[nvec[2]]*NoiseDict[nvec[2]]))
                    eq2ndOrderMoment = collect(eq2ndOrderMoment, M_2(NoiseDict[nvec[0]]*NoiseDict[nvec[1]]))
                    eq2ndOrderMoment = collect(eq2ndOrderMoment, M_2(NoiseDict[nvec[0]]*NoiseDict[nvec[2]]))
                    eq2ndOrderMoment = collect(eq2ndOrderMoment, M_2(NoiseDict[nvec[1]]*NoiseDict[nvec[2]]))
                else:
                    eq2ndOrderMoment = collect(eq2ndOrderMoment, M_2(NoiseDict[nvec[0]]*NoiseDict[nvec[0]]))
                    eq2ndOrderMoment = collect(eq2ndOrderMoment, M_2(NoiseDict[nvec[1]]*NoiseDict[nvec[1]]))
                    eq2ndOrderMoment = collect(eq2ndOrderMoment, M_2(NoiseDict[nvec[2]]*NoiseDict[nvec[2]]))
                    eq2ndOrderMoment = collect(eq2ndOrderMoment, M_2(NoiseDict[nvec[3]]*NoiseDict[nvec[3]]))
                    eq2ndOrderMoment = collect(eq2ndOrderMoment, M_2(NoiseDict[nvec[0]]*NoiseDict[nvec[1]]))
                    eq2ndOrderMoment = collect(eq2ndOrderMoment, M_2(NoiseDict[nvec[0]]*NoiseDict[nvec[2]]))
                    eq2ndOrderMoment = collect(eq2ndOrderMoment, M_2(NoiseDict[nvec[0]]*NoiseDict[nvec[3]]))
                    eq2ndOrderMoment = collect(eq2ndOrderMoment, M_2(NoiseDict[nvec[1]]*NoiseDict[nvec[2]]))
                    eq2ndOrderMoment = collect(eq2ndOrderMoment, M_2(NoiseDict[nvec[1]]*NoiseDict[nvec[3]]))
                    eq2ndOrderMoment = collect(eq2ndOrderMoment, M_2(NoiseDict[nvec[2]]*NoiseDict[nvec[3]]))
                    
                eq2ndOrderMoment = eq2ndOrderMoment.simplify()
                if eq2ndOrderMoment not in EQsys2ndOrdMom:
                    EQsys2ndOrdMom.append(eq2ndOrderMoment)
                if M_2(NoiseDict[noise1]*NoiseDict[noise2]) not in EOM_2ndOrderMom:
                    EOM_2ndOrderMom[M_2(NoiseDict[noise1]*NoiseDict[noise2])] = eq2ndOrderMoment
                    NoiseSubs2ndOrder[M_2(NoiseDict[noise1]*NoiseDict[noise2])] = r'\left< \vphantom{Dg}\right.' +latex(NoiseDict[noise1]*NoiseDict[noise2]) + r'\left. \vphantom{Dg}\right>' 
      
    return EQsys1stOrdMom, EOM_1stOrderMom, NoiseSubs1stOrder, EQsys2ndOrdMom, EOM_2ndOrderMom, NoiseSubs2ndOrder 


## calculates noise in the system
# returns analytical solution for stationary noise
def _getNoiseStationarySol(_getNoiseEOM, _getFokkerPlanckEquation, _get_orderedLists_vKE, stoich):
    P, M_1, M_2, t = symbols('P M_1 M_2 t')
    
    EQsys1stOrdMom, EOM_1stOrderMom, NoiseSubs1stOrder, EQsys2ndOrdMom, EOM_2ndOrderMom, NoiseSubs2ndOrder = _getNoiseEOM(_getFokkerPlanckEquation, _get_orderedLists_vKE, stoich)
    
    nvec = []
    for key1 in stoich:
        for key2 in stoich[key1]:
            if key2 != 'rate' and stoich[key1][key2] != 'const':
                if not key2 in nvec:
                    nvec.append(key2)
    nvec = sorted(nvec, key=default_sort_key)
    assert (len(nvec)==2 or len(nvec)==3 or len(nvec)==4), 'This module works for 2, 3 or 4 different reactants only'

    NoiseDict = {}
    for kk in range(len(nvec)):
        NoiseDict[nvec[kk]] = Symbol('eta_'+str(nvec[kk]))
            
    if len(NoiseDict)==2:
        SOL_1stOrderMom = solve(EQsys1stOrdMom, [M_1(NoiseDict[nvec[0]]),M_1(NoiseDict[nvec[1]])], dict=True)
    elif len(NoiseDict)==3:
        SOL_1stOrderMom = solve(EQsys1stOrdMom, [M_1(NoiseDict[nvec[0]]),M_1(NoiseDict[nvec[1]]),M_1(NoiseDict[nvec[2]])], dict=True)
    else:
        SOL_1stOrderMom = solve(EQsys1stOrdMom, [M_1(NoiseDict[nvec[0]]),M_1(NoiseDict[nvec[1]]),M_1(NoiseDict[nvec[2]]),M_1(NoiseDict[nvec[3]])], dict=True)
    
                    
    SOL_2ndOrdMomDict = {} 
    if len(NoiseDict)==2:
        SOL_2ndOrderMom = list(linsolve(EQsys2ndOrdMom, [M_2(NoiseDict[nvec[0]]*NoiseDict[nvec[0]]), M_2(NoiseDict[nvec[1]]*NoiseDict[nvec[1]]), M_2(NoiseDict[nvec[0]]*NoiseDict[nvec[1]])]))[0] #only one set of solutions (if any) in linear system of equations
        
        if M_2(NoiseDict[nvec[0]]*NoiseDict[nvec[1]]) in SOL_2ndOrderMom:
            ZsubDict = {M_2(NoiseDict[nvec[0]]*NoiseDict[nvec[1]]): 0}
            SOL_2ndOrderMomMod = []
            for nn in range(len(SOL_2ndOrderMom)):
                SOL_2ndOrderMomMod.append(SOL_2ndOrderMom[nn].subs(ZsubDict))
            SOL_2ndOrderMom = SOL_2ndOrderMomMod
        SOL_2ndOrdMomDict[M_2(NoiseDict[nvec[0]]*NoiseDict[nvec[0]])] = SOL_2ndOrderMom[0]
        SOL_2ndOrdMomDict[M_2(NoiseDict[nvec[1]]*NoiseDict[nvec[1]])] = SOL_2ndOrderMom[1]
        SOL_2ndOrdMomDict[M_2(NoiseDict[nvec[0]]*NoiseDict[nvec[1]])] = SOL_2ndOrderMom[2]
    
    elif len(NoiseDict)==3:
        SOL_2ndOrderMom = list(linsolve(EQsys2ndOrdMom, [M_2(NoiseDict[nvec[0]]*NoiseDict[nvec[0]]), 
                                                         M_2(NoiseDict[nvec[1]]*NoiseDict[nvec[1]]), 
                                                         M_2(NoiseDict[nvec[2]]*NoiseDict[nvec[2]]), 
                                                         M_2(NoiseDict[nvec[0]]*NoiseDict[nvec[1]]), 
                                                         M_2(NoiseDict[nvec[0]]*NoiseDict[nvec[2]]), 
                                                         M_2(NoiseDict[nvec[1]]*NoiseDict[nvec[2]])]))[0] #only one set of solutions (if any) in linear system of equations; hence index [0]
        ZsubDict = {}
        for noise1 in NoiseDict:
            for noise2 in NoiseDict:
                if M_2(NoiseDict[noise1]*NoiseDict[noise2]) in SOL_2ndOrderMom:
                    ZsubDict[M_2(NoiseDict[noise1]*NoiseDict[noise2])] = 0
        if len(ZsubDict) > 0:
            SOL_2ndOrderMomMod = []
            for nn in range(len(SOL_2ndOrderMom)):
                SOL_2ndOrderMomMod.append(SOL_2ndOrderMom[nn].subs(ZsubDict))
        SOL_2ndOrderMom = SOL_2ndOrderMomMod
        SOL_2ndOrdMomDict[M_2(NoiseDict[nvec[0]]*NoiseDict[nvec[0]])] = SOL_2ndOrderMom[0]
        SOL_2ndOrdMomDict[M_2(NoiseDict[nvec[1]]*NoiseDict[nvec[1]])] = SOL_2ndOrderMom[1]
        SOL_2ndOrdMomDict[M_2(NoiseDict[nvec[2]]*NoiseDict[nvec[2]])] = SOL_2ndOrderMom[2]
        SOL_2ndOrdMomDict[M_2(NoiseDict[nvec[0]]*NoiseDict[nvec[1]])] = SOL_2ndOrderMom[3]
        SOL_2ndOrdMomDict[M_2(NoiseDict[nvec[0]]*NoiseDict[nvec[2]])] = SOL_2ndOrderMom[4]
        SOL_2ndOrdMomDict[M_2(NoiseDict[nvec[1]]*NoiseDict[nvec[2]])] = SOL_2ndOrderMom[5]
        
    else:
        SOL_2ndOrderMom = list(linsolve(EQsys2ndOrdMom, [M_2(NoiseDict[nvec[0]]*NoiseDict[nvec[0]]), 
                                                         M_2(NoiseDict[nvec[1]]*NoiseDict[nvec[1]]), 
                                                         M_2(NoiseDict[nvec[2]]*NoiseDict[nvec[2]]),
                                                         M_2(NoiseDict[nvec[3]]*NoiseDict[nvec[3]]), 
                                                         M_2(NoiseDict[nvec[0]]*NoiseDict[nvec[1]]), 
                                                         M_2(NoiseDict[nvec[0]]*NoiseDict[nvec[2]]), 
                                                         M_2(NoiseDict[nvec[0]]*NoiseDict[nvec[3]]),
                                                         M_2(NoiseDict[nvec[1]]*NoiseDict[nvec[2]]),
                                                         M_2(NoiseDict[nvec[1]]*NoiseDict[nvec[3]]),
                                                         M_2(NoiseDict[nvec[2]]*NoiseDict[nvec[3]])]))[0] #only one set of solutions (if any) in linear system of equations; hence index [0]
        ZsubDict = {}
        for noise1 in NoiseDict:
            for noise2 in NoiseDict:
                if M_2(NoiseDict[noise1]*NoiseDict[noise2]) in SOL_2ndOrderMom:
                    ZsubDict[M_2(NoiseDict[noise1]*NoiseDict[noise2])] = 0
        if len(ZsubDict) > 0:
            SOL_2ndOrderMomMod = []
            for nn in range(len(SOL_2ndOrderMom)):
                SOL_2ndOrderMomMod.append(SOL_2ndOrderMom[nn].subs(ZsubDict))
        SOL_2ndOrderMom = SOL_2ndOrderMomMod
        SOL_2ndOrdMomDict[M_2(NoiseDict[nvec[0]]*NoiseDict[nvec[0]])] = SOL_2ndOrderMom[0]
        SOL_2ndOrdMomDict[M_2(NoiseDict[nvec[1]]*NoiseDict[nvec[1]])] = SOL_2ndOrderMom[1]
        SOL_2ndOrdMomDict[M_2(NoiseDict[nvec[2]]*NoiseDict[nvec[2]])] = SOL_2ndOrderMom[2]
        SOL_2ndOrdMomDict[M_2(NoiseDict[nvec[3]]*NoiseDict[nvec[3]])] = SOL_2ndOrderMom[3]
        SOL_2ndOrdMomDict[M_2(NoiseDict[nvec[0]]*NoiseDict[nvec[1]])] = SOL_2ndOrderMom[4]
        SOL_2ndOrdMomDict[M_2(NoiseDict[nvec[0]]*NoiseDict[nvec[2]])] = SOL_2ndOrderMom[5]
        SOL_2ndOrdMomDict[M_2(NoiseDict[nvec[0]]*NoiseDict[nvec[3]])] = SOL_2ndOrderMom[6]
        SOL_2ndOrdMomDict[M_2(NoiseDict[nvec[1]]*NoiseDict[nvec[2]])] = SOL_2ndOrderMom[7]
        SOL_2ndOrdMomDict[M_2(NoiseDict[nvec[1]]*NoiseDict[nvec[3]])] = SOL_2ndOrderMom[8]
        SOL_2ndOrdMomDict[M_2(NoiseDict[nvec[2]]*NoiseDict[nvec[3]])] = SOL_2ndOrderMom[9]    
      
    return SOL_1stOrderMom[0], NoiseSubs1stOrder, SOL_2ndOrdMomDict, NoiseSubs2ndOrder 
 

# def _getNoise(_getFokkerPlanckEquation, _get_orderedLists_vKE, stoich):
#     P, M_1, M_2, t = symbols('P M_1 M_2 t')
#     
#     nvec = []
#     for key1 in stoich:
#         for key2 in stoich[key1]:
#             if not key2 == 'rate':
#                 if not key2 in nvec:
#                     nvec.append(key2)
#     nvec = sorted(nvec, key=default_sort_key)
#     assert (len(nvec)==2 or len(nvec)==3 or len(nvec)==4), 'This module works for 2, 3 or 4 different reactants only'
# 
#     NoiseDict = {}
#     for kk in range(len(nvec)):
#         NoiseDict[nvec[kk]] = Symbol('eta_'+str(nvec[kk]))
#     FPEdict, substring = _getFokkerPlanckEquation(_get_orderedLists_vKE, stoich)
#     print(len(NoiseDict))
#     
#     NoiseSub1stOrder = {}
#     NoiseSub2ndOrder = {}
#     
#     if len(NoiseDict)==2:
#         Pdim = P(NoiseDict[nvec[0]],NoiseDict[nvec[1]],t)
#     elif len(NoiseDict)==3:
#         Pdim = P(NoiseDict[nvec[0]],NoiseDict[nvec[1]],NoiseDict[nvec[2]],t)
#     else:
#         Pdim = P(NoiseDict[nvec[0]],NoiseDict[nvec[1]],NoiseDict[nvec[2]],NoiseDict[nvec[3]],t)
#         
#     for noise1 in NoiseDict:
#         NoiseSub1stOrder[NoiseDict[noise1]*Pdim] = M_1(NoiseDict[noise1])
#         for noise2 in NoiseDict:
#             for noise3 in NoiseDict:
#                 key = NoiseDict[noise1]*NoiseDict[noise2]*Derivative(Pdim,NoiseDict[noise3])
#                 if key not in NoiseSub1stOrder:
#                     if NoiseDict[noise1] == NoiseDict[noise2] and NoiseDict[noise3] == NoiseDict[noise1]:
#                         NoiseSub1stOrder[key] = -2*M_1(NoiseDict[noise1])
#                     elif NoiseDict[noise1] != NoiseDict[noise2] and NoiseDict[noise3] == NoiseDict[noise1]:
#                         NoiseSub1stOrder[key] = -M_1(NoiseDict[noise2])
#                     elif NoiseDict[noise1] != NoiseDict[noise2] and NoiseDict[noise3] == NoiseDict[noise2]:
#                         NoiseSub1stOrder[key] = -M_1(NoiseDict[noise1])
#                     elif NoiseDict[noise1] != NoiseDict[noise3] and NoiseDict[noise3] != NoiseDict[noise2]:
#                         NoiseSub1stOrder[key] = 0
#                     else:
#                         NoiseSub1stOrder[key] = 0 
#                 key2 = NoiseDict[noise1]*Derivative(Pdim,NoiseDict[noise2],NoiseDict[noise3])
#                 if key2 not in NoiseSub1stOrder:
#                     NoiseSub1stOrder[key2] = 0   
#     
#     for noise1 in NoiseDict:
#         for noise2 in NoiseDict:
#             key = NoiseDict[noise1]*NoiseDict[noise2]*Pdim
#             if key not in NoiseSub2ndOrder:
#                 NoiseSub2ndOrder[key] = M_2(NoiseDict[noise1]*NoiseDict[noise2])
#             for noise3 in NoiseDict:
#                 for noise4 in NoiseDict:
#                     key2 = NoiseDict[noise1]*NoiseDict[noise2]*NoiseDict[noise3]*Derivative(Pdim,NoiseDict[noise4])
#                     if key2 not in NoiseSub2ndOrder:
#                         if noise1 == noise2 and noise2 == noise3 and noise3 == noise4:
#                             NoiseSub2ndOrder[key2] = -3*M_2(NoiseDict[noise1]*NoiseDict[noise1])
#                         elif noise1 == noise2 and noise2 != noise3 and noise1 == noise4:
#                             NoiseSub2ndOrder[key2] = -2*M_2(NoiseDict[noise1]*NoiseDict[noise3])
#                         elif noise1 == noise2 and noise2 != noise3 and noise3 == noise4:
#                             NoiseSub2ndOrder[key2] = -M_2(NoiseDict[noise1]*NoiseDict[noise2])
#                         elif noise1 != noise2 and noise2 == noise3 and noise1 == noise4:
#                             NoiseSub2ndOrder[key2] = -M_2(NoiseDict[noise2]*NoiseDict[noise3])
#                         elif noise1 != noise2 and noise2 == noise3 and noise3 == noise4:
#                             NoiseSub2ndOrder[key2] = -2*M_2(NoiseDict[noise1]*NoiseDict[noise2])
#                         elif noise1 != noise2 and noise2 != noise3 and noise1 != noise3:
#                             if noise1 == noise4:
#                                 NoiseSub2ndOrder[key2] = -M_2(NoiseDict[noise2]*NoiseDict[noise3])
#                             elif noise2 == noise4:
#                                 NoiseSub2ndOrder[key2] = -M_2(NoiseDict[noise1]*NoiseDict[noise3])
#                             elif noise3 == noise4:
#                                 NoiseSub2ndOrder[key2] = -M_2(NoiseDict[noise1]*NoiseDict[noise2])
#                             else:
#                                 NoiseSub2ndOrder[key2] = 0
#                         else:
#                             NoiseSub2ndOrder[key2] = 0
#                     key3 = NoiseDict[noise1]*NoiseDict[noise2]*Derivative(Pdim,NoiseDict[noise3],NoiseDict[noise4])
#                     if key3 not in NoiseSub2ndOrder:
#                         if noise1 == noise3 and noise2 == noise4:
#                             if noise1 == noise2:
#                                 NoiseSub2ndOrder[key3] = 2
#                             else:
#                                  NoiseSub2ndOrder[key3] = 1
#                         elif noise1 == noise4 and noise2 == noise3:
#                             if noise1 == noise2:
#                                 NoiseSub2ndOrder[key3] = 2
#                             else:
#                                 NoiseSub2ndOrder[key3] = 1
#                         else:
#                             NoiseSub2ndOrder[key3] = 0
#     NoiseSubs1stOrder = {}                   
#     EQsys1stOrdMom = []
#     EOM_1stOrderMom = {}
#     for fpe_lhs in FPEdict: 
#         for noise in NoiseDict:
#             eq1stOrderMoment = (NoiseDict[noise]*FPEdict[fpe_lhs]).expand() 
#             eq1stOrderMoment = eq1stOrderMoment.subs(NoiseSub1stOrder)
#             EQsys1stOrdMom.append(eq1stOrderMoment)
#             if M_1(NoiseDict[noise]) not in EOM_1stOrderMom:
#                 EOM_1stOrderMom[M_1(NoiseDict[noise])] = eq1stOrderMoment
#                 NoiseSubs1stOrder[M_1(NoiseDict[noise])] = r'<'+latex(NoiseDict[noise])+'>'
#     print(EOM_1stOrderMom)
#             
#     if len(NoiseDict)==2:
#         SOL_1stOrderMom = solve(EQsys1stOrdMom, [M_1(NoiseDict[nvec[0]]),M_1(NoiseDict[nvec[1]])], dict=True)
#     elif len(NoiseDict)==3:
#         SOL_1stOrderMom = solve(EQsys1stOrdMom, [M_1(NoiseDict[nvec[0]]),M_1(NoiseDict[nvec[1]]),M_1(NoiseDict[nvec[2]])], dict=True)
#     else:
#         SOL_1stOrderMom = solve(EQsys1stOrdMom, [M_1(NoiseDict[nvec[0]]),M_1(NoiseDict[nvec[1]]),M_1(NoiseDict[nvec[2]]),M_1(NoiseDict[nvec[3]])], dict=True)
#     print(SOL_1stOrderMom)
#     
#     NoiseSubs2ndOrder = {}
#     EQsys2ndOrdMom = []
#     EOM_2ndOrderMom = {}
#     for fpe_lhs in FPEdict: 
#         for noise1 in NoiseDict:
#             for noise2 in NoiseDict:
#                 eq2ndOrderMoment = (NoiseDict[noise1]*NoiseDict[noise2]*FPEdict[fpe_lhs]).expand() 
#                 eq2ndOrderMoment = eq2ndOrderMoment.subs(NoiseSub2ndOrder)
#                 eq2ndOrderMoment = eq2ndOrderMoment.subs(NoiseSub1stOrder)
#                 eq2ndOrderMoment = eq2ndOrderMoment.subs(SOL_1stOrderMom[0])
#                 if len(NoiseDict)==2:
#                     eq2ndOrderMoment = collect(eq2ndOrderMoment, M_2(NoiseDict[nvec[0]]*NoiseDict[nvec[0]]))
#                     eq2ndOrderMoment = collect(eq2ndOrderMoment, M_2(NoiseDict[nvec[1]]*NoiseDict[nvec[1]]))
#                     eq2ndOrderMoment = collect(eq2ndOrderMoment, M_2(NoiseDict[nvec[0]]*NoiseDict[nvec[1]]))
#                 elif len(NoiseDict)==3:
#                     eq2ndOrderMoment = collect(eq2ndOrderMoment, M_2(NoiseDict[nvec[0]]*NoiseDict[nvec[0]]))
#                     eq2ndOrderMoment = collect(eq2ndOrderMoment, M_2(NoiseDict[nvec[1]]*NoiseDict[nvec[1]]))
#                     eq2ndOrderMoment = collect(eq2ndOrderMoment, M_2(NoiseDict[nvec[2]]*NoiseDict[nvec[2]]))
#                     eq2ndOrderMoment = collect(eq2ndOrderMoment, M_2(NoiseDict[nvec[0]]*NoiseDict[nvec[1]]))
#                     eq2ndOrderMoment = collect(eq2ndOrderMoment, M_2(NoiseDict[nvec[0]]*NoiseDict[nvec[2]]))
#                     eq2ndOrderMoment = collect(eq2ndOrderMoment, M_2(NoiseDict[nvec[1]]*NoiseDict[nvec[2]]))
#                 else:
#                     eq2ndOrderMoment = collect(eq2ndOrderMoment, M_2(NoiseDict[nvec[0]]*NoiseDict[nvec[0]]))
#                     eq2ndOrderMoment = collect(eq2ndOrderMoment, M_2(NoiseDict[nvec[1]]*NoiseDict[nvec[1]]))
#                     eq2ndOrderMoment = collect(eq2ndOrderMoment, M_2(NoiseDict[nvec[0]]*NoiseDict[nvec[1]]))
#                 eq2ndOrderMoment = eq2ndOrderMoment.simplify()
#                 if eq2ndOrderMoment not in EQsys2ndOrdMom:
#                     EQsys2ndOrdMom.append(eq2ndOrderMoment)
#                 if M_2(NoiseDict[noise1]*NoiseDict[noise2]) not in EOM_2ndOrderMom:
#                     EOM_2ndOrderMom[M_2(NoiseDict[noise1]*NoiseDict[noise2])] = eq2ndOrderMoment
#                     NoiseSubs2ndOrder[M_2(NoiseDict[noise1]*NoiseDict[noise2])] = r'<'+latex(NoiseDict[noise1]*NoiseDict[noise2])+'>'
#     print(EOM_2ndOrderMom)
#                     
#     SOL_2ndOrdMomDict = {} 
#     if len(NoiseDict)==2:
#         SOL_2ndOrderMom = list(linsolve(EQsys2ndOrdMom, [M_2(NoiseDict[nvec[0]]*NoiseDict[nvec[0]]), M_2(NoiseDict[nvec[1]]*NoiseDict[nvec[1]]), M_2(NoiseDict[nvec[0]]*NoiseDict[nvec[1]])]))[0] #only one set of solutions (if any) in linear system of equations
#         
#         if M_2(NoiseDict[nvec[0]]*NoiseDict[nvec[1]]) in SOL_2ndOrderMom:
#             ZsubDict = {M_2(NoiseDict[nvec[0]]*NoiseDict[nvec[1]]): 0}
#             SOL_2ndOrderMomMod = []
#             for nn in range(len(SOL_2ndOrderMom)):
#                 SOL_2ndOrderMomMod.append(SOL_2ndOrderMom[nn].subs(ZsubDict))
#             SOL_2ndOrderMom = SOL_2ndOrderMomMod
#         SOL_2ndOrdMomDict[M_2(NoiseDict[nvec[0]]*NoiseDict[nvec[0]])] = SOL_2ndOrderMom[0]
#         SOL_2ndOrdMomDict[M_2(NoiseDict[nvec[1]]*NoiseDict[nvec[1]])] = SOL_2ndOrderMom[1]
#         SOL_2ndOrdMomDict[M_2(NoiseDict[nvec[0]]*NoiseDict[nvec[1]])] = SOL_2ndOrderMom[2]
#     
#     elif len(NoiseDict)==3:
#         SOL_2ndOrderMom = list(linsolve(EQsys2ndOrdMom, [M_2(NoiseDict[nvec[0]]*NoiseDict[nvec[0]]), 
#                                                          M_2(NoiseDict[nvec[1]]*NoiseDict[nvec[1]]), 
#                                                          M_2(NoiseDict[nvec[2]]*NoiseDict[nvec[2]]), 
#                                                          M_2(NoiseDict[nvec[0]]*NoiseDict[nvec[1]]), 
#                                                          M_2(NoiseDict[nvec[0]]*NoiseDict[nvec[2]]), 
#                                                          M_2(NoiseDict[nvec[1]]*NoiseDict[nvec[2]])]))[0] #only one set of solutions (if any) in linear system of equations; hence index [0]
#         ZsubDict = {}
#         for noise1 in NoiseDict:
#             for noise2 in NoiseDict:
#                 if M_2(NoiseDict[noise1]*NoiseDict[noise2]) in SOL_2ndOrderMom:
#                     ZsubDict[M_2(NoiseDict[noise1]*NoiseDict[noise2])] = 0
#         if len(ZsubDict) > 0:
#             SOL_2ndOrderMomMod = []
#             for nn in range(len(SOL_2ndOrderMom)):
#                 SOL_2ndOrderMomMod.append(SOL_2ndOrderMom[nn].subs(ZsubDict))
#         SOL_2ndOrderMom = SOL_2ndOrderMomMod
#         SOL_2ndOrdMomDict[M_2(NoiseDict[nvec[0]]*NoiseDict[nvec[0]])] = SOL_2ndOrderMom[0]
#         SOL_2ndOrdMomDict[M_2(NoiseDict[nvec[1]]*NoiseDict[nvec[1]])] = SOL_2ndOrderMom[1]
#         SOL_2ndOrdMomDict[M_2(NoiseDict[nvec[2]]*NoiseDict[nvec[2]])] = SOL_2ndOrderMom[2]
#         SOL_2ndOrdMomDict[M_2(NoiseDict[nvec[0]]*NoiseDict[nvec[1]])] = SOL_2ndOrderMom[3]
#         SOL_2ndOrdMomDict[M_2(NoiseDict[nvec[0]]*NoiseDict[nvec[2]])] = SOL_2ndOrderMom[4]
#         SOL_2ndOrdMomDict[M_2(NoiseDict[nvec[1]]*NoiseDict[nvec[2]])] = SOL_2ndOrderMom[5]
#     print(SOL_2ndOrdMomDict)    
#       
#     return EOM_1stOrderMom, SOL_1stOrderMom[0], NoiseSubs1stOrder, EOM_2ndOrderMom, SOL_2ndOrdMomDict, NoiseSubs2ndOrder 
    

## Function that returns the ODE system deerived from Master equation
def _getODEs_vKE(_get_orderedLists_vKE, stoich):
    P, t = symbols('P t')
    V = Symbol('V', real=True, constant=True)
    Vlist_lhs, Vlist_rhs, substring = _get_orderedLists_vKE(stoich)
    rhsODE=0
    lhsODE=0
    for kk in range(len(Vlist_rhs)):
        for key in Vlist_rhs[kk]:
            if key==sqrt(V):
                rhsODE += Vlist_rhs[kk][key]            
    for kk in range(len(Vlist_lhs)):
        for key in Vlist_lhs[kk]:
            if key==sqrt(V):
                lhsODE += Vlist_lhs[kk][key]  
        
    ODE = lhsODE-rhsODE
    
    nvec = []
    for key1 in stoich:
        for key2 in stoich[key1]:
            if key2 != 'rate' and stoich[key1][key2] != 'const':
                if not key2 in nvec:
                    nvec.append(key2)
    #for reactant in reactants:
    #    nvec.append(reactant)
    nvec = sorted(nvec, key=default_sort_key)
    assert (len(nvec)==2 or len(nvec)==3 or len(nvec)==4), 'This module works for 2, 3 or 4 different reactants only'
    
    PhiDict = {}
    NoiseDict = {}
    for kk in range(len(nvec)):
        NoiseDict[nvec[kk]] = Symbol('eta_'+str(nvec[kk]))
        PhiDict[nvec[kk]] = Symbol('Phi_'+str(nvec[kk]))
        
    PhiSubDict = None    
    if not substring == None:
        PhiSubDict = {}
        for sub in substring:
            PhiSubSym = Symbol('Phi_'+str(sub))
            PhiSubDict[PhiSubSym] = substring[sub]
        for key in PhiSubDict:
            for sym in PhiSubDict[key].atoms(Symbol):
                phisub = Symbol('Phi_'+str(sym))
                if sym in nvec:
                    symSub = phisub
                    PhiSubDict[key] = PhiSubDict[key].subs({sym: symSub})
                else:
                    PhiSubDict[key] = PhiSubDict[key].subs({sym: 1}) #here we assume that if a reactant in the substitution string is not a time-dependent reactant it can only be the total number of reactants which is constant, i.e. 1=N/N
    
    
    if len(Vlist_lhs)-1 == 2:
        ode1 = 0
        ode2 = 0
        for kk in range(len(ODE.args)):
            prod=1
            for nn in range(len(ODE.args[kk].args)-1):
                prod *= ODE.args[kk].args[nn]
            if ODE.args[kk].args[-1] == Derivative(P(NoiseDict[nvec[0]],NoiseDict[nvec[1]],t), NoiseDict[nvec[0]]):
                ode1 += prod
            elif ODE.args[kk].args[-1] == Derivative(P(NoiseDict[nvec[0]],NoiseDict[nvec[1]],t), NoiseDict[nvec[1]]):
                ode2 += prod
            else:
                print('Check ODE.args!')
                
        if PhiSubDict:
            ode1 = ode1.subs(PhiSubDict)
            ode2 = ode2.subs(PhiSubDict) 
            
            for key in PhiSubDict:
                if key == PhiDict[nvec[0]]:
                    ODE_2 = solve(ode2, Derivative(PhiDict[nvec[1]] , t), dict=True)
                    ODEsys = {**ODE_2[0]}
                elif key == PhiDict[nvec[1]]:
                    ODE_1 = solve(ode1, Derivative(PhiDict[nvec[0]] , t), dict=True)
                    ODEsys = {**ODE_1[0]}
                else:
                    ODE_1 = solve(ode1, Derivative(PhiDict[nvec[0]] , t), dict=True)
                    ODE_2 = solve(ode2, Derivative(PhiDict[nvec[1]] , t), dict=True)
                    ODEsys = {**ODE_1[0], **ODE_2[0]}            
        else:        
            ODE_1 = solve(ode1, Derivative(PhiDict[nvec[0]] , t), dict=True)
            ODE_2 = solve(ode2, Derivative(PhiDict[nvec[1]] , t), dict=True)
            ODEsys = {**ODE_1[0], **ODE_2[0]}
                
    elif len(Vlist_lhs)-1 == 3:
        ode1 = 0
        ode2 = 0
        ode3 = 0
        for kk in range(len(ODE.args)):
            prod=1
            for nn in range(len(ODE.args[kk].args)-1):
                prod *= ODE.args[kk].args[nn]
            if ODE.args[kk].args[-1] == Derivative(P(NoiseDict[nvec[0]],NoiseDict[nvec[1]],NoiseDict[nvec[2]],t), NoiseDict[nvec[0]]):
                ode1 += prod
            elif ODE.args[kk].args[-1] == Derivative(P(NoiseDict[nvec[0]],NoiseDict[nvec[1]],NoiseDict[nvec[2]],t), NoiseDict[nvec[1]]):
                ode2 += prod
            else:
                ode3 += prod
        
        if PhiSubDict:
            ode1 = ode1.subs(PhiSubDict)
            ode2 = ode2.subs(PhiSubDict)
            ode3 = ode3.subs(PhiSubDict)
            
            for key in PhiSubDict:
                if key == PhiDict[nvec[0]]:
                    ODE_2 = solve(ode2, Derivative(PhiDict[nvec[1]] , t), dict=True)
                    ODE_3 = solve(ode3, Derivative(PhiDict[nvec[2]] , t), dict=True)
                    ODEsys = {**ODE_2[0], **ODE_3[0]}
                elif key == PhiDict[nvec[1]]:
                    ODE_1 = solve(ode1, Derivative(PhiDict[nvec[0]] , t), dict=True)
                    ODE_3 = solve(ode3, Derivative(PhiDict[nvec[2]] , t), dict=True)
                    ODEsys = {**ODE_1[0], **ODE_3[0]}
                elif key == PhiDict[nvec[2]]:
                    ODE_1 = solve(ode1, Derivative(PhiDict[nvec[0]] , t), dict=True)
                    ODE_2 = solve(ode2, Derivative(PhiDict[nvec[1]] , t), dict=True)
                    ODEsys = {**ODE_1[0], **ODE_2[0]}
                else:
                    ODE_1 = solve(ode1, Derivative(PhiDict[nvec[0]] , t), dict=True)
                    ODE_2 = solve(ode2, Derivative(PhiDict[nvec[1]] , t), dict=True)
                    ODE_3 = solve(ode3, Derivative(PhiDict[nvec[2]] , t), dict=True)
                    ODEsys = {**ODE_1[0], **ODE_2[0], **ODE_3[0]} 
        
        else:
            ODE_1 = solve(ode1, Derivative(PhiDict[nvec[0]] , t), dict=True)
            ODE_2 = solve(ode2, Derivative(PhiDict[nvec[1]] , t), dict=True)
            ODE_3 = solve(ode3, Derivative(PhiDict[nvec[2]] , t), dict=True)
            ODEsys = {**ODE_1[0], **ODE_2[0], **ODE_3[0]}
            
    elif len(Vlist_lhs)-1 == 4:
        ode1 = 0
        ode2 = 0
        ode3 = 0
        ode4 = 0
        for kk in range(len(ODE.args)):
            prod=1
            for nn in range(len(ODE.args[kk].args)-1):
                prod *= ODE.args[kk].args[nn]
            if ODE.args[kk].args[-1] == Derivative(P(NoiseDict[nvec[0]],NoiseDict[nvec[1]],NoiseDict[nvec[2]],NoiseDict[nvec[3]],t), NoiseDict[nvec[0]]):
                ode1 += prod
            elif ODE.args[kk].args[-1] == Derivative(P(NoiseDict[nvec[0]],NoiseDict[nvec[1]],NoiseDict[nvec[2]],NoiseDict[nvec[3]],t), NoiseDict[nvec[1]]):
                ode2 += prod
            elif ODE.args[kk].args[-1] == Derivative(P(NoiseDict[nvec[0]],NoiseDict[nvec[1]],NoiseDict[nvec[2]],NoiseDict[nvec[3]],t), NoiseDict[nvec[2]]):
                ode3 += prod
            else:
                ode4 += prod
        
        if PhiSubDict:
            ode1 = ode1.subs(PhiSubDict)
            ode2 = ode2.subs(PhiSubDict)
            ode3 = ode3.subs(PhiSubDict)
            ode4 = ode4.subs(PhiSubDict)
            
            for key in PhiSubDict:
                if key == PhiDict[nvec[0]]:
                    ODE_2 = solve(ode2, Derivative(PhiDict[nvec[1]] , t), dict=True)
                    ODE_3 = solve(ode3, Derivative(PhiDict[nvec[2]] , t), dict=True)
                    ODE_4 = solve(ode4, Derivative(PhiDict[nvec[3]] , t), dict=True)
                    ODEsys = {**ODE_2[0], **ODE_3[0], **ODE_4[0]}
                elif key == PhiDict[nvec[1]]:
                    ODE_1 = solve(ode1, Derivative(PhiDict[nvec[0]] , t), dict=True)
                    ODE_3 = solve(ode3, Derivative(PhiDict[nvec[2]] , t), dict=True)
                    ODE_4 = solve(ode4, Derivative(PhiDict[nvec[3]] , t), dict=True)
                    ODEsys = {**ODE_1[0], **ODE_3[0], **ODE_4[0]}
                elif key == PhiDict[nvec[2]]:
                    ODE_1 = solve(ode1, Derivative(PhiDict[nvec[0]] , t), dict=True)
                    ODE_2 = solve(ode2, Derivative(PhiDict[nvec[1]] , t), dict=True)
                    ODE_4 = solve(ode4, Derivative(PhiDict[nvec[3]] , t), dict=True)
                    ODEsys = {**ODE_1[0], **ODE_2[0], **ODE_4[0]}
                elif key == PhiDict[nvec[3]]:
                    ODE_1 = solve(ode1, Derivative(PhiDict[nvec[0]] , t), dict=True)
                    ODE_2 = solve(ode2, Derivative(PhiDict[nvec[1]] , t), dict=True)
                    ODE_3 = solve(ode3, Derivative(PhiDict[nvec[2]] , t), dict=True)
                    ODEsys = {**ODE_1[0], **ODE_2[0], **ODE_3[0]}
                else:
                    ODE_1 = solve(ode1, Derivative(PhiDict[nvec[0]] , t), dict=True)
                    ODE_2 = solve(ode2, Derivative(PhiDict[nvec[1]] , t), dict=True)
                    ODE_3 = solve(ode3, Derivative(PhiDict[nvec[2]] , t), dict=True)
                    ODE_4 = solve(ode4, Derivative(PhiDict[nvec[3]] , t), dict=True)
                    ODEsys = {**ODE_1[0], **ODE_2[0], **ODE_3[0], **ODE_4[0]} 
        
        else:
            ODE_1 = solve(ode1, Derivative(PhiDict[nvec[0]] , t), dict=True)
            ODE_2 = solve(ode2, Derivative(PhiDict[nvec[1]] , t), dict=True)
            ODE_3 = solve(ode3, Derivative(PhiDict[nvec[2]] , t), dict=True)
            ODE_4 = solve(ode4, Derivative(PhiDict[nvec[3]] , t), dict=True)
            ODEsys = {**ODE_1[0], **ODE_2[0], **ODE_3[0], **ODE_4[0]}
            
    else:
        print('Not implemented yet.')
        
    return ODEsys
 




    
def _raiseModelError(expected, read, rule):
    raise SyntaxError("Expected " + expected + " but read '" + read + "' in rule: " + rule)


## generic method for constructing figures in MuMoTview and MuMoTmultiController classes
def _buildFig(object, figure = None):
    global figureCounter
    object._figureNum = figureCounter
    figureCounter += 1
    plt.ion()
    with warnings.catch_warnings(): # ignore warnings when plt.hold has been deprecated in installed libraries - still need to try plt.hold(True) in case older libraries in use
        warnings.filterwarnings("ignore",category=MatplotlibDeprecationWarning)
        warnings.filterwarnings("ignore",category=UserWarning)
        plt.hold(True)  
    if figure == None:
        object._figure = plt.figure(object._figureNum) 
    else:
        object._figure = figure

## used for determining significant digits for axes formatting in plots MuMoTstreamView and MuMoTbifurcationView 
def round_to_1(x):
    if x == 0: return 1
    return round(x, -int(floor(log10(abs(x)))))

## Function for editing properties of 3D plots. 
#
#This function is used in MuMoTvectorView.
def _fig_formatting_3D(figure, xlab=None, ylab=None, zlab=None, ax_reformat=False, 
                       specialPoints=None, showFixedPoints=False, **kwargs):
    
    fig = plt.gcf()
    #fig.set_size_inches(10,8) 
    ax = fig.gca(projection='3d')
    
    if kwargs.get('showPlane', False) == True:
        pointsMesh = np.linspace(0, 1, 11)
        Xdat, Ydat = np.meshgrid(pointsMesh, pointsMesh)
        Zdat = 1 - Xdat - Ydat
        Zdat[Zdat<0] = 0
        ax.plot_surface(Xdat, Ydat, Zdat, rstride=20, cstride=20, color='grey', alpha=0.25)
    
    if xlab==None:
        try:
            xlabelstr = ax.xaxis.get_label_text()
            if len(ax.xaxis.get_label_text())==0:
                xlabelstr = 'choose x-label'
        except:
            xlabelstr = 'choose x-label'
    else:
        xlabelstr = xlab
        
    if ylab==None:
        try:
            ylabelstr = ax.yaxis.get_label_text()
            if len(ax.yaxis.get_label_text())==0:
                ylabelstr = 'choose y-label'
        except:
            ylabelstr = 'choose y-label'
    else:
        ylabelstr = ylab
        
    if zlab==None:
        try:
            zlabelstr = ax.yaxis.get_label_text()
            if len(ax.zaxis.get_label_text())==0:
                zlabelstr = 'choose z-label'
        except:
            zlabelstr = 'choose z-label'
    else:
        zlabelstr = zlab
    
    x_lim_left = ax.get_xbound()[0]#ax.xaxis.get_data_interval()[0]
    x_lim_right = ax.get_xbound()[1]#ax.xaxis.get_data_interval()[1]
    y_lim_bot = ax.get_ybound()[0]#ax.yaxis.get_data_interval()[0]
    y_lim_top = ax.get_ybound()[1]
    z_lim_bot = ax.get_zbound()[0]#ax.zaxis.get_data_interval()[0]
    z_lim_top = ax.get_zbound()[1]
    if ax_reformat==False:
        xmajortickslocs = ax.xaxis.get_majorticklocs()
        #xminortickslocs = ax.xaxis.get_minorticklocs()
        ymajortickslocs = ax.yaxis.get_majorticklocs()
        #yminortickslocs = ax.yaxis.get_minorticklocs()
        zmajortickslocs = ax.zaxis.get_majorticklocs()
        #zminortickslocs = ax.zaxis.get_minorticklocs()
        #plt.cla()
        ax.set_xticks(xmajortickslocs)
        #ax.set_xticks(xminortickslocs, minor = True)
        ax.set_yticks(ymajortickslocs)
        #ax.set_yticks(yminortickslocs, minor = True)
        ax.set_zticks(zmajortickslocs)
        #ax.set_zticks(zminortickslocs, minor = True)
    else:
        max_xrange = x_lim_right - x_lim_left
        max_yrange = y_lim_top - y_lim_bot
        if kwargs.get('showPlane', False) == True:
            max_zrange = z_lim_top
        else:
            max_zrange = z_lim_top - z_lim_bot
            
        if max_xrange < 1.0:
            xMLocator_major = round_to_1(max_xrange/4)
        else:
            xMLocator_major = round_to_1(max_xrange/6)
        #xMLocator_minor = xMLocator_major/2
        if max_yrange < 1.0:
            yMLocator_major = round_to_1(max_yrange/4)
        else:
            yMLocator_major = round_to_1(max_yrange/6)
        #yMLocator_minor = yMLocator_major/2
        if max_zrange < 1.0:
            zMLocator_major = round_to_1(max_zrange/4)
        else:
            zMLocator_major = round_to_1(max_zrange/6)
        #zMLocator_minor = yMLocator_major/2
        ax.xaxis.set_major_locator(ticker.MultipleLocator(xMLocator_major))
        #ax.xaxis.set_minor_locator(ticker.MultipleLocator(xMLocator_minor))
        ax.yaxis.set_major_locator(ticker.MultipleLocator(yMLocator_major))
        #ax.yaxis.set_minor_locator(ticker.MultipleLocator(yMLocator_minor))
        ax.zaxis.set_major_locator(ticker.MultipleLocator(zMLocator_major))
        #ax.zaxis.set_minor_locator(ticker.MultipleLocator(zMLocator_minor))
        
    ax.set_xlim3d(x_lim_left,x_lim_right)
    ax.set_ylim3d(y_lim_bot,y_lim_top)
    if kwargs.get('showPlane', False) == True:
        ax.set_zlim3d(0,z_lim_top)
    else:
        ax.set_zlim3d(z_lim_bot,z_lim_top)
                    
    if showFixedPoints==True:
        if not specialPoints[0] == []:
            for jj in range(len(specialPoints[0])):
                try:
                    len(specialPoints[3][jj]) == 3
                    lam1 = specialPoints[3][jj][0]
                    lam2 = specialPoints[3][jj][1]
                    lam3 = specialPoints[3][jj][2]
                    if (re(lam1) < 0 and re(lam2) < 0 and re(lam3) < 0):
                        FPcolor = 'g'
                        FPmarker = 'o'
                    else:
                        FPcolor = 'r'  
                        FPmarker = '>'     
                except:
                    print('Check input!')
                    FPcolor='k'  
                     
                ax.scatter([specialPoints[0][jj]], [specialPoints[1][jj]], [specialPoints[2][jj]], 
                           marker=FPmarker, s=300, c=FPcolor)
    
    if 'fontsize' in kwargs:
        if not kwargs['fontsize']==None:
            chooseFontSize = kwargs['fontsize']
    elif len(xlabelstr) > 40 or len(ylabelstr) > 40 or len(zlabelstr) > 40:
        chooseFontSize = 16
    elif 31 <= len(xlabelstr) <= 40 or 31 <= len(ylabelstr) <= 40 or 31 <= len(zlabelstr) <= 40:
        chooseFontSize = 20
    elif 26 <= len(xlabelstr) <= 30 or 26 <= len(ylabelstr) <= 30 or 26 <= len(zlabelstr) <= 30:
        chooseFontSize = 26
    else:
        chooseFontSize = 30
    
    ax.xaxis.labelpad = 20
    ax.yaxis.labelpad = 20
    ax.zaxis.labelpad = 20
    ax.set_xlabel(r''+str(xlabelstr), fontsize = chooseFontSize)
    ax.set_ylabel(r''+str(ylabelstr), fontsize = chooseFontSize)
    if len(str(zlabelstr))>1:
        ax.set_zlabel(r''+str(zlabelstr), fontsize = chooseFontSize, rotation=90)
    else:
        ax.set_zlabel(r''+str(zlabelstr), fontsize = chooseFontSize)
        
    for tick in ax.xaxis.get_major_ticks():
        tick.label.set_fontsize(18) 
    for tick in ax.yaxis.get_major_ticks():
        tick.label.set_fontsize(18)
    for tick in ax.zaxis.get_major_ticks():
        tick.set_pad(8)
        tick.label.set_fontsize(18)      
        
    plt.tight_layout(pad=4)
 

## Function for formatting 2D plots. 
#
#This function is used in MuMoTvectorView, MuMoTstreamView and MuMoTbifurcationView    
def _fig_formatting_2D(figure=None, xdata=None, ydata=None, choose_xrange=None, choose_yrange=None, eigenvalues=None, 
                       curve_replot=False, ax_reformat=False, showFixedPoints=False, specialPoints=None,
                       xlab=None, ylab=None, curvelab=None, **kwargs):
    #print(kwargs)
    
    linestyle_list = ['solid','dashed', 'dashdot', 'dotted', 'solid','dashed', 'dashdot', 'dotted', 'solid']
    
    if xdata and ydata:
        if len(xdata) == len(ydata):
            #plt.figure(figsize=(8,6), dpi=80)
            ax = plt.axes()
            data_x=xdata
            data_y=ydata
            
        else:
            print('CHECK input:')
            print('xdata and ydata are lists of arrays and must have same lengths!')
            print('Array pairs xdata[k] and ydata[k] (k = 0, ..., N-1) must have same lengths too!')

    elif figure:
        plt.gcf()
        ax = plt.gca()
        data_x = [ax.lines[kk].get_xdata() for kk in range(len(ax.lines))]
        data_y = [ax.lines[kk].get_ydata() for kk in range(len(ax.lines))]
        
    else:
        print('Choose either figure or dataset(s)')
    #print(data_x)
    
    if xlab==None:
        try:
            xlabelstr = ax.xaxis.get_label_text()
            if len(ax.xaxis.get_label_text())==0:
                xlabelstr = 'choose x-label'
        except:
            xlabelstr = 'choose x-label'
    else:
        xlabelstr = xlab
        
    if ylab==None:
        try:
            ylabelstr = ax.yaxis.get_label_text()
            if len(ax.yaxis.get_label_text())==0:
                ylabelstr = 'choose y-label'
        except:
            ylabelstr = 'choose y-label'
    else:
        ylabelstr = ylab
    
    if ax_reformat==False and figure!=None:
        xmajortickslocs = ax.xaxis.get_majorticklocs()
        xminortickslocs = ax.xaxis.get_minorticklocs()
        ymajortickslocs = ax.yaxis.get_majorticklocs()
        yminortickslocs = ax.yaxis.get_minorticklocs()
        x_lim_left = ax.get_xbound()[0]#ax.xaxis.get_data_interval()[0]
        x_lim_right = ax.get_xbound()[1]#ax.xaxis.get_data_interval()[1]
        y_lim_bot = ax.get_ybound()[0]#ax.yaxis.get_data_interval()[0]
        y_lim_top = ax.get_ybound()[1]#ax.yaxis.get_data_interval()[1]
        #print(ax.yaxis.get_data_interval())
        
    if curve_replot==True:
        plt.cla()
    
    if ax_reformat==False and figure!=None:
        ax.set_xticks(xmajortickslocs)
        ax.set_xticks(xminortickslocs, minor = True)
        ax.set_yticks(ymajortickslocs)
        ax.set_yticks(yminortickslocs, minor = True)
        ax.tick_params(axis = 'both', which = 'major', length=5, width=2)
        ax.tick_params(axis = 'both', which = 'minor', length=3, width=1)
        plt.xlim(x_lim_left,x_lim_right)
        plt.ylim(y_lim_bot,y_lim_top)
        
    if figure==None or curve_replot==True:
        if 'LineThickness' in kwargs:
            LineThickness = kwargs['LineThickness']
        else:
            LineThickness = 4
        
        if eigenvalues:
            solX_dict={} #bifurcation parameter
            solY_dict={} #state variable 1
            solX_dict['solX_unst']=[] 
            solY_dict['solY_unst']=[]
            solX_dict['solX_stab']=[]
            solY_dict['solY_stab']=[]
            solX_dict['solX_saddle']=[]
            solY_dict['solY_saddle']=[]
            
            nr_sol_unst=0
            nr_sol_saddle=0
            nr_sol_stab=0
            data_x_tmp=[]
            data_y_tmp=[]
            #print(specialPoints)
            for nn in range(len(data_x)):
                #sign_change=0
                for kk in range(len(eigenvalues[nn])):
                    if kk > 0:
                        if (np.sign(np.real(eigenvalues[nn][kk][0]))*np.sign(np.real(eigenvalues[nn][kk-1][0])) < 0
                            or np.sign(np.real(eigenvalues[nn][kk][1]))*np.sign(np.real(eigenvalues[nn][kk-1][1])) < 0):
                            #print('sign change')
                            #sign_change+=1
                            #print(sign_change)
                            #if specialPoints !=None and specialPoints[0]!=[]:
                            #    data_x_tmp.append(specialPoints[0][sign_change-1])
                            #    data_y_tmp.append(specialPoints[1][sign_change-1])
                            
                            if nr_sol_unst == 1:
                                solX_dict['solX_unst'].append(data_x_tmp)
                                solY_dict['solY_unst'].append(data_y_tmp)
                            elif nr_sol_saddle == 1:
                                solX_dict['solX_saddle'].append(data_x_tmp)
                                solY_dict['solY_saddle'].append(data_y_tmp)
                            elif nr_sol_stab == 1:
                                solX_dict['solX_stab'].append(data_x_tmp)
                                solY_dict['solY_stab'].append(data_y_tmp)
                            else:
                                print('Something went wrong!')
                            
                            data_x_tmp_first=data_x_tmp[-1]
                            data_y_tmp_first=data_y_tmp[-1]
                            nr_sol_stab=0
                            nr_sol_saddle=0
                            nr_sol_unst=0
                            data_x_tmp=[]
                            data_y_tmp=[]
                            data_x_tmp.append(data_x_tmp_first)
                            data_y_tmp.append(data_y_tmp_first)
                            #if specialPoints !=None and specialPoints[0]!=[]:
                            #    data_x_tmp.append(specialPoints[0][sign_change-1])
                            #    data_y_tmp.append(specialPoints[1][sign_change-1])
                                    
                    if np.real(eigenvalues[nn][kk][0]) < 0 and np.real(eigenvalues[nn][kk][1]) < 0:  
                        nr_sol_stab=1
                    elif np.real(eigenvalues[nn][kk][0]) > 0 and np.real(eigenvalues[nn][kk][1]) < 0:
                        nr_sol_saddle=1
                    elif np.real(eigenvalues[nn][kk][0]) < 0 and np.real(eigenvalues[nn][kk][1]) > 0:
                        nr_sol_saddle=1
                    else:
                        nr_sol_unst=1
                        
                    data_x_tmp.append(data_x[nn][kk])
                    data_y_tmp.append(data_y[nn][kk])
                
                    if kk == len(eigenvalues[nn])-1:
                        if nr_sol_unst == 1:
                            solX_dict['solX_unst'].append(data_x_tmp)
                            solY_dict['solY_unst'].append(data_y_tmp)
                        elif nr_sol_saddle == 1:
                            solX_dict['solX_saddle'].append(data_x_tmp)
                            solY_dict['solY_saddle'].append(data_y_tmp)
                        elif nr_sol_stab == 1:
                            solX_dict['solX_stab'].append(data_x_tmp)
                            solY_dict['solY_stab'].append(data_y_tmp)
                        else:
                            print('Something went wrong!')
                        
                
            if not solX_dict['solX_unst'] == []:            
                for jj in range(len(solX_dict['solX_unst'])):
                    plt.plot(solX_dict['solX_unst'][jj], 
                             solY_dict['solY_unst'][jj], 
                             c = line_color_list[2], 
                             ls = linestyle_list[3], lw = LineThickness, label = r'unstable')
            if not solX_dict['solX_stab'] == []:            
                for jj in range(len(solX_dict['solX_stab'])):
                    plt.plot(solX_dict['solX_stab'][jj], 
                             solY_dict['solY_stab'][jj], 
                             c = line_color_list[1], 
                             ls = linestyle_list[0], lw = LineThickness, label = r'stable')
            if not solX_dict['solX_saddle'] == []:            
                for jj in range(len(solX_dict['solX_saddle'])):
                    plt.plot(solX_dict['solX_saddle'][jj], 
                             solY_dict['solY_saddle'][jj], 
                             c = line_color_list[0], 
                             ls = linestyle_list[1], lw = LineThickness, label = r'saddle')
                                    
                            
        else:
            for nn in range(len(data_x)):
                try:
                    plt.plot(data_x[nn], data_y[nn], c = line_color_list[nn], 
                             ls = linestyle_list[nn], lw = LineThickness, label = r''+str(curvelab[nn]))
                except:
                    plt.plot(data_x[nn], data_y[nn], c = line_color_list[nn], 
                             ls = linestyle_list[nn], lw = LineThickness)
        
        
    if len(xlabelstr) > 40 or len(ylabelstr) > 40:
        chooseFontSize = 16
    elif 31 <= len(xlabelstr) <= 40 or 31 <= len(ylabelstr) <= 40:
        chooseFontSize = 20
    elif 26 <= len(xlabelstr) <= 30 or 26 <= len(ylabelstr) <= 30:
        chooseFontSize = 26
    else:
        chooseFontSize = 30
        
    if 'fontsize' in kwargs:
        if not kwargs['fontsize']==None:
            chooseFontSize = kwargs['fontsize']

    plt.xlabel(r''+str(xlabelstr), fontsize = chooseFontSize)
    plt.ylabel(r''+str(ylabelstr), fontsize = chooseFontSize)
    #ax.set_xlabel(r''+str(xlabelstr), fontsize = chooseFontSize)
    #ax.set_ylabel(r''+str(ylabelstr), fontsize = chooseFontSize)
     
    if figure==None or ax_reformat==True:
        if choose_xrange:
            max_xrange = choose_xrange[1]-choose_xrange[0]
        else:
            xrange = [np.max(data_x[kk]) - np.min(data_x[kk]) for kk in range(len(data_x))]
            max_xrange = max(xrange)
        
        if choose_yrange:
            max_yrange = choose_yrange[1]-choose_yrange[0]
        else:
            yrange = [np.max(data_y[kk]) - np.min(data_y[kk]) for kk in range(len(data_y))]
            max_yrange = max(yrange) 
        
        if max_xrange < 1.0:
            xMLocator_major = round_to_1(max_xrange/5)
        else:
            xMLocator_major = round_to_1(max_xrange/10)
        xMLocator_minor = xMLocator_major/2
        if max_yrange < 1.0:
            yMLocator_major = round_to_1(max_yrange/5)
        else:
            yMLocator_major = round_to_1(max_yrange/10)
        yMLocator_minor = yMLocator_major/2
        
        if choose_xrange:
            plt.xlim(choose_xrange[0]-xMLocator_minor, choose_xrange[1]+xMLocator_minor)
        else:
            plt.xlim(np.min(data_x)-xMLocator_minor, np.max(data_x)+xMLocator_minor)
        if choose_yrange:
            plt.ylim(choose_yrange[0]-yMLocator_minor, choose_yrange[1]+yMLocator_minor)
        else:
            plt.ylim(np.min(data_y)-yMLocator_minor, np.max(data_y)+yMLocator_minor)

        ax.xaxis.set_major_locator(ticker.MultipleLocator(xMLocator_major))
        ax.xaxis.set_minor_locator(ticker.MultipleLocator(xMLocator_minor))
        ax.yaxis.set_major_locator(ticker.MultipleLocator(yMLocator_major))
        ax.yaxis.set_minor_locator(ticker.MultipleLocator(yMLocator_minor))
        for axis in ['top','bottom','left','right']:
            ax.spines[axis].set_linewidth(2)
        
        ax.tick_params('both', length=5, width=2, which='major')
        ax.tick_params('both', length=3, width=1, which='minor')
    
    if eigenvalues:
        if not specialPoints[0] == []:
            for jj in range(len(specialPoints[0])):
                plt.plot([specialPoints[0][jj]], [specialPoints[1][jj]], marker='o', markersize=15, 
                         c=line_color_list[-1])    
            for a,b,c in zip(specialPoints[0], specialPoints[1], specialPoints[2]): 
                if a > plt.xlim()[0]+(plt.xlim()[1]-plt.xlim()[0])/2:
                    x_offset = -(plt.xlim()[1]-plt.xlim()[0])*0.02
                else:
                    x_offset = (plt.xlim()[1]-plt.xlim()[0])*0.02
                if b > plt.ylim()[0]+(plt.ylim()[1]-plt.ylim()[0])/2:
                    y_offset = -(plt.ylim()[1]-plt.ylim()[0])*0.05
                else:
                    y_offset = (plt.ylim()[1]-plt.ylim()[0])*0.05
                plt.text(a+x_offset, b+y_offset, c, fontsize=18)
    
    if showFixedPoints==True:
        if not specialPoints[0] == []:
            for jj in range(len(specialPoints[0])):
                try:
                    len(specialPoints[2][jj]) == 2
                    lam1 = specialPoints[2][jj][0]
                    lam2 = specialPoints[2][jj][1]
                    if re(lam1) < 0 and re(lam2) < 0:
                        FPcolor = line_color_list[1]
                        FPfill = 'full'
                    elif re(lam1) > 0 and re(lam2) > 0:
                        FPcolor = line_color_list[2]
                        FPfill = 'none'
                    else:
                        FPcolor = line_color_list[0]
                        FPfill = 'none'
                        
                except:
                    print('Check input!')
                    FPcolor=line_color_list[-1]  
                    FPfill = 'none'
                     
                plt.plot([specialPoints[0][jj]], [specialPoints[1][jj]], marker='o', markersize=12, 
                         c=FPcolor, fillstyle=FPfill, mew=4, mec=FPcolor)
    if kwargs.get('grid', False) == True:
        plt.grid()
        
    if curvelab != None:
        #if 'legend_loc' in kwargs:
        #    legend_loc = kwargs['legend_loc']
        #else:
        #    legend_loc = 'upper left'
        legend_loc = kwargs.get('legend_loc', 'upper left')
        plt.legend(loc=str(legend_loc), fontsize=20, ncol=2)
        
    for tick in ax.xaxis.get_major_ticks():
                    tick.label.set_fontsize(18) 
    for tick in ax.yaxis.get_major_ticks():
                    tick.label.set_fontsize(18)
    plt.tight_layout() 
    
def _decodeNetworkTypeFromString(netTypeStr):
    # init the network type
    admissibleNetTypes = {'full': NetworkType.FULLY_CONNECTED, 
                          'erdos-renyi': NetworkType.ERSOS_RENYI, 
                          'barabasi-albert': NetworkType.BARABASI_ALBERT, 
                          'dynamic': NetworkType.DYNAMIC}
    
    if netTypeStr not in admissibleNetTypes:
        print("ERROR! Invalid network type argument! Valid strings are: " + str(admissibleNetTypes) )
    return admissibleNetTypes.get(netTypeStr, None)

def _encodeNetworkTypeToString(netType):
    # init the network type
    netTypeEncoding = {NetworkType.FULLY_CONNECTED: 'full', 
                          NetworkType.ERSOS_RENYI: 'erdos-renyi', 
                          NetworkType.BARABASI_ALBERT: 'barabasi-albert', 
                          NetworkType.DYNAMIC: 'dynamic'}
    
    if netType not in netTypeEncoding:
        print("ERROR! Invalid netTypeEncoding table! Tryed to encode network type: " + str(netType) )
    return netTypeEncoding.get(netType, 'none')

def _make_autopct(values):
    def my_autopct(pct):
        total = sum(values)
        val = int(round(pct*total/100.0))
        return '{p:.2f}%  ({v:d})'.format(p=pct,v=val)
    return my_autopct
