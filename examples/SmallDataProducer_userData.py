# importing generic python modules
import numpy as np
import psana
import time
import argparse
import socket
import os
import RegDB.experiment_info
from smalldata_tools.DetObject import DetObject
from smalldata_tools.utilities import checkDet, printMsg
from smalldata_tools.SmallDataUtils import setParameter, getUserData, getUserEnvData, detData, defaultDetectors
from smalldata_tools.SmallDataDefaultDetector import ttRawDetector, wave8Detector, epicsDetector
from smalldata_tools.roi_rebin import ROIFunc, spectrumFunc, projectionFunc, sparsifyFunc
from smalldata_tools.waveformFunc import getCMPeakFunc, templateFitFunc
from smalldata_tools.droplet import dropletFunc
from smalldata_tools.photons import photonFunc
from smalldata_tools.azimuthalBinning import AzimuthalBinning

########################################################## 
##
## User Input start --> 
##
########################################################## 
##########################################################
# functions for run dependant parameters
##########################################################
def getAzIntParams(run):
    if isinstance(run,basestring):
        run=int(run)
        
    ret_dict = {'eBeam': 9.5}
    ret_dict['cspad_center'] = [87526.79161840, 92773.3296889500]
    ret_dict['cspad_dis_to_sam'] = 80.
    return ret_dict

def getROI_cspad(run):
    if isinstance(run,basestring):
        run=int(run)
    if run <=6:
        return [ [[0,1], [1,74], [312,381]],
                 [[8,9], [8,89], [218,303]] ]
    else:
        return [ [[0,1], [1,74], [312,381]],
                 [[8,9], [8,89], [218,303]] ]

def getROI_rowland(run):
    if isinstance(run,basestring):
        run=int(run)

    if run <= 6:
        return [[[0,1], [25, 275], [516, 556]], 
                [[0,1], [25, 275], [460, 500]]]
    else:
        return [[[0,1], [25, 275], [516, 556]], 
                [[0,1], [25, 275], [460, 500]]]

def getNmaxDrop(run):
    if isinstance(run,basestring):
        run=int(run)

    if run >= 10:
        return 2000
    else:
        return 400

##########################################################
# run independent parameters 
##########################################################
#aliases for experiment specific PVs go here
#epicsPV = ['slit_s1_hw'] 
epicsPV = []
#fix timetool calibration if necessary
#ttCalib=[0.,2.,0.]
ttCalib=[]
#ttCalib=[1.860828, -0.002950]
#decide which analog input to save & give them nice names
#aioParams=[[1],['laser']]
aioParams=[]
########################################################## 
##
## <-- User Input end
##
########################################################## 


##########################################################
#command line input parameter: definitions & reading
##########################################################
maxNevt=1e9
gatherInterval=100
dirname = None
parser = argparse.ArgumentParser()
parser.add_argument("--run", help="run")
parser.add_argument("--exp", help="experiment name")
parser.add_argument("--nevt", help="number of events", type=int)
parser.add_argument("--dir", help="directory for output files (def <exp>/hdf5/smalldata)")
parser.add_argument("--offline", help="run offline (def for current exp from ffb)")
parser.add_argument("--gather", help="gather interval (def 100)", type=int)
parser.add_argument("--live", help="add data to redis database (quasi-live feedback)", action='store_true')
parser.add_argument("--liveFast", help="add data to redis database (quasi-live feedback)", action='store_true')
parser.add_argument("--norecorder", help="ignore recorder streams", action='store_true')
args = parser.parse_args()

hostname=socket.gethostname()
if not args.run:
    run=raw_input("Run Number:\n")
else:
    run=args.run
if not args.exp:
    hutches=['amo','sxr','xpp','xcs','mfx','cxi','mec']
    hutch=None
    for thisHutch in hutches:
        if hostname.find(thisHutch)>=0:
            hutch=thisHutch.upper()
    if hutch is None:
        #then check current path
        path=os.getcwd()
        for thisHutch in hutches:
            if path.find(thisHutch)>=0:
                hutch=thisHutch.upper()
    if hutch is None:
        print 'cannot figure out which experiment to use, please specify -e <expname> on commandline'
        import sys
        sys.exit()
    expname=RegDB.experiment_info.active_experiment(hutch)[1]
    dsname='exp='+expname+':run='+run+':smd:dir=/reg/d/ffb/%s/%s/xtc:live'%(hutch.lower(),expname)
    #data gets removed from ffb faster now, please check if data is still available
    isLive = (RegDB.experiment_info.experiment_runs(hutch)[-1]['end_time_unix'] is None)
    if not isLive:
        xtcdirname = '/reg/d/ffb/%s/%s/xtc'%(hutch.lower(),expname)
        xtcname=xtcdirname+'/e*-r%04d-*'%int(run)
        import glob
        presentXtc=glob.glob('%s'%xtcname)
        if len(presentXtc)==0:
            dsname='exp='+expname+':run='+run+':smd'
else:
    expname=args.exp
    hutch=expname[0:3]
    dsname='exp='+expname+':run='+run+':smd'
if args.offline:
    dsname='exp='+expname+':run='+run+':smd'
if args.gather:
    gatherInterval=args.gather
if args.nevt:
    maxNevt=args.nevt
if args.dir:
    dirname=args.dir
    if dirname[-1]=='/':
        dirname=dirname[:-1]

if args.norecorder:
    dsname=dsname+':stream=0-79'

debug = True
time_ev_sum = 0.
try:
    ds = psana.MPIDataSource(dsname)
except:
    print 'failed to make MPIDataSource for ',dsname
    import sys
    sys.exit()

try:    
    if dirname is None:
        dirname = '/reg/d/psdm/%s/%s/hdf5/smalldata'%(hutch.lower(),expname)
    smldataFile = '%s/%s_Run%03d.h5'%(dirname,expname,int(run))

    smldata = ds.small_data(smldataFile,gather_interval=gatherInterval)

except:
    print 'failed making the output file ',smldataFile
    import sys
    sys.exit()

if ds.rank==0:
    version='unable to detect psana version'
    for dirn in psana.__file__.split('/'):
        if dirn.find('ana-')>=0:
            version=dirn
    print 'Using psana version ',version


########################################################## 
##
## Setting up the default detectors
## needs to be before the user detectors only for epix10k 
## data that needs ghost corrections and uses a psana 
## detector that does not take the event as inpu (EPICS PV, tt)
##
########################################################## 
defaultDets = defaultDetectors(hutch)
if len(ttCalib)>0:
    setParameter(defaultDets, ttCalib)
if len(aioParams)>0:
    setParameter(defaultDets, aioParams, 'ai')
if len(epicsPV)>0:
    defaultDets.append(epicsDetector(PVlist=epicsPV, name='epicsUser'))

##adding wave8 traces:
#defaultDets.append(wave8Detector('Wave8WF'))
##adding raw timetool traces:
#try:
#    defaultDets.append(ttRawDetector(env=ds.env()))
#except:
#    pass

########################################################## 
##
## User Input start --> 
##
########################################################## 
dets=[]

epixname='epix_diff'
nDrop = getNmaxDrop(int(run))
have_epix = checkDet(ds.env(), epixname)
if have_epix:
    #create detector object. needs run for calibration data
    #common mode: 46 is the "original" to psana method 7(?)
    #row & column correction on data w/ photons&neighbors removed.
    epix = DetObject(epixname ,ds.env(), int(run), common_mode=46)

    #two threshold droplet finding.
    #for data w/ > 1 photon energy this is the only thing that will work.
    #Tends to add photons together into single droplet if occupancy
    #is not low, might need photonizing step to get single photon positions
    droplet = droplet(threshold=10., thresholdLow=3., thresADU=0.,name='droplet')
    specFunc_300=spectrumFunc(name='spec_300',bins=[0,300,5.])
    droplet.addFunc(specFunc_300) 
    #droplet.addDropletSave(maxDroplets=nDrop)
    epix.addFund(droplet)

    #now add photon algorithms. Only works for single energy photon data
    # ADU_per_photon: expected ADU for photon of expected energy
    # thresADU: fraction of photon energy in photon candidate
                #(2 neighboring pixel)
    #retImg: 0 (def): only histogram of 0,1,2,3,...,24 photons/pixel is returned
    #        1 return Nphot, x, y arrays
    #        2 store image using photons /event
    if (int(run)==444):
        epix.addFunc(photon(ADU_per_photon=165, thresADU=0.9, retImg=2, nphotMax=200))

    dets.append(epix)

ROI_rowland = getROI_rowland(int(run))
if checkDet(ds.env(), 'cs140_diff'):
    cs140 = DetObject('cs140_diff' ,ds.env(), int(run))#, name='Rowland')
    for iROI,ROI in enumerate(ROI_rowland):
        cs140.addFunc(ROIFunc(ROI=ROI, name='ROI_%d'%iROI))
    dets.append(cs140)

azIntParams = getAzIntParams(run)
ROI_cspad = getROI_cspad(int(run))
haveCspad = checkDet(ds.env(), 'cspad')
if haveCspad:
    cspad = DetObject('cspad' ,ds.env(), int(run), name='cspad')
    for iROI,ROI in enumerate(ROI_cspad):
        cspad.addFunc(ROIFunc(ROI=ROI, name='ROI_%d'%iROI))

    cspad.azav_eBeam=azIntParams['eBeam']
    if azIntParams.has_key('cspad_center'):
        try:
            azav = AzimuthalBinning(center=azIntParams['cspad_center'], dis_to_sam=azIntParams['cspad_dis_to_sam'], phiBins=11, Pplane=0)
            cspad.addFunc(azav)
        except:
	        pass


    cspad.storeSum(sumAlgo='calib')
    cspad.storeSum(sumAlgo='square')
    dets.append(cspad)

########################################################## 
##
## <-- User Input end
##
########################################################## 
dets = [ det for det in dets if checkDet(ds.env(), det._srcName)]
#for now require all area detectors in run to also be present in event.


#add config data here
userDataCfg={}
for det in defaultDets:
    userDataCfg[det.name] = det.params_as_dict()
for det in dets:
    userDataCfg[det._name] = det.params_as_dict()
#for det in raredets:
#    userDataCfg[det._name] = det.params_as_dict()
Config={'UserDataCfg':userDataCfg}
smldata.save(Config)

for eventNr,evt in enumerate(ds.events()):
    printMsg(eventNr, evt.run(), ds.rank, ds.size)

    if eventNr >= maxNevt/ds.size:
        break

    #add default data
    defData = detData(defaultDets, evt)
    #for key in defData.keys():
    #    print eventNr, key, defData[key]
    smldata.event(defData)

    #detector data using DetObject 
    userDict = {}
    for det in dets:
        try:
            #this should be a plain dict. Really.
            det.getData(evt)
            det.processFuncs()
            userDict[det._name]=getUserData(det)
            try:
                envData=getUserEnvData(det)
                if len(envData.keys())>0:
                    userDict[det._name+'_env']=envData
            except:
                pass
            #print userDict[det._name]
        except:
            pass
    smldata.event(userDict)

    #here you can add any data you like: example is a product of the maximumof two area detectors.
    #try:
    #    cspadMax = cspad.evt.dat.max()
    #    epix_vonHamosMax = epix_vonHamos.evt.dat.max()
    #    combDict = {'userValue': cspadMax*epix_vonHamosMax}
    #    smldata.event(combDict)
    #except:
    #    pass

    #first event.
    if ds.rank==0 and eventNr==0 and (args.live or args.liveFast):
        if not args.liveFast:
            #this saves all fields
            smldata.connect_redis()
        else:
            redisKeys = defaultRedisVars(hutch)
            redisList=['fiducials','event_time']
            for key in redisKeys:
                if key.find('/')>=0 and key in smldata._dlist.keys():
                    redisList.append(key)
                else:
                    for sdkey in smldata._dlist.keys():
                        if sdkey.find(key)>=0:
                            redisList.append(sdkey)
            print 'Saving in REDIS: ',redisList
            smldata.connect_redis(redisList)

sumDict={'Sums': {}}
for det in dets:
    for key in det.storeSum().keys():
        sumData=smldata.sum(det.storeSum()[key])
        sumDict['Sums']['%s_%s'%(det._name, key)]=sumData
if len(sumDict['Sums'].keys())>0:
    smldata.save(sumDict)

print 'rank %d on %s is finished'%(ds.rank, hostname)
smldata.save()
