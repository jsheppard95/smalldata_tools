# importing generic python modules
import numpy as np
import psana
import time
import argparse
import socket
import os
import logging

from smalldata_tools.DetObject import DetObject
from smalldata_tools.utilities import checkDet, printMsg
from smalldata_tools.SmallDataUtils import setParameter, getUserData, getUserEnvData, detData, defaultDetectors
from smalldata_tools.SmallDataDefaultDetector import epicsDetector
from smalldata_tools.roi_rebin import ROIFunc, spectrumFunc, projectionFunc, sparsifyFunc, imageFunc

#from smalldata_tools import defaultDetectors,epicsDetector,printMsg,detData
#from smalldata_tools import checkDet,getCfgOutput,getUserData,getUserEnvData,dropObject
#from smalldata_tools import ttRawDetector,wave8Detector,setParameter
from smalldata_tools.DetObject import DetObject
from smalldata_tools.droplet import dropletFunc
from smalldata_tools.photons import photonFunc
########################################################## 
##
## User Input start --> 
##
########################################################## 
##########################################################
# functions for run dependant parameters
##########################################################

def getNmaxDrop(run):
    if isinstance(run,basestring):
        run=int(run)

    if run == 103:
        return 15000
    else:
        return 10

##########################################################
# run independent parameters 
##########################################################
#aliases for experiment specific PVs go here
#epicsPV = ['ccm_alio_position07']
epicsPV = []
#fix timetool calibration if necessary
#ttCalib=[0.,2.,0.]
ttCalib=[]#1.860828, -0.002950]
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

    ws_url = "https://pswww.slac.stanford.edu/ws/lgbk"
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    station = 0
    resp = requests.get(ws_url + "/lgbk/ws/activeexperiment_for_instrument_station", {"instrument_name": hutch, "station": station})
    expname = resp.json().get("value", {}).get("name")
    if (hutch == 'cxi'):
        print('We will assume you are using the experiment for the primary CXI station (%s), is you are using the SSC please pass the experiment name using -e <expname>'%expname)

    dsname='exp='+expname+':run='+run+':smd:dir=/reg/d/ffb/%s/%s/xtc:live'%(hutch.lower(),expname)
    #data gets removed from ffb faster now, please check if data is still available
    rundoc = requests.get(ws_url + "/lgbk/" + exp  + "/ws/current_run").json()["value"]
    isLive = False
    if not rundoc:
        logger.error("Invalid response from server")
        if not rundoc.get('end_time', None):
            isLive = True
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
    for dirn in psana.__file__:
        if dirn.find('ana-')>=0:
            version=dirn
    print 'Using psana version ',version
########################################################## 
##
## User Input start --> 
##
########################################################## 
dets=[]

nDrop = getNmaxDrop(int(run))
have_andor = checkDet(ds.env(), 'andor')
if have_andor:
    andor = DetObject('andor' ,ds.env(), int(run), common_mode=0)
    
    roi = ROIFunc(writeArea=True)
    roi.addFunc(spectrumFunc(bins=[-50,550,2.5]))
    andor.addFunc(roi)

    photon = photonFunc(ADU_per_photon=350)
    ##photon.addFunc(ROIFunc(ROI=[[0,1e6],[0,1e6]], writeArea=True))
    ##photon.addFunc(spectrumFunc(bins=[0,10,1.]))
    ##photon.addFunc(projectionFunc(axis=0))
    photon.addFunc(sparsifyFunc(nData=100))
    andor.addFunc(photon)

    droplet = dropletFunc(threshold=30, thresholdLow=30, useRms=False, name='droplet30ADU')
    ##droplet = droplet(threshold=10., thresholdLow=3., thresADU=0.,name='droplet')
    droplet.addFunc(sparsifyFunc(nData=350))#, needProps=True))
    droplet.addFunc(spectrumFunc(bins=[0,3500,10.]))
    andor.addFunc(droplet)

    droplet = dropletFunc(threshold=10, thresholdLow=4)
    droplet.addFunc(sparsifyFunc(nData=350))#, needProps=True))
    droplet.addFunc(spectrumFunc(bins=[0,3500,10.]))
    andor.addFunc(droplet)

    droplet = dropletFunc(threshold=4, thresholdLow=4, name='droplet44')
    droplet.addFunc(sparsifyFunc(nData=350))#, needProps=True))
    droplet.addFunc(spectrumFunc(bins=[0,3500,10.]))
    andor.addFunc(droplet)

    droplet = dropletFunc(threshold=10, thresholdLow=10, name='droplet1010')
    droplet.addFunc(sparsifyFunc(nData=600))#, needProps=True))
    droplet.addFunc(spectrumFunc(bins=[0,3500,10.]))
    andor.addFunc(droplet)
    
    dets.append(andor)

acqirisName = 'Acq02'
haveAcqiris = checkDet(ds.env(), acqirisName)
if haveAcqiris:
    acqiris = DetObject(acqirisName ,ds.env(), int(run), name=acqirisName)
    fullArea=ROIFunc(writeArea=True)
    acqiris.addFunc(fullArea)
    dets.append(acqiris)


########################################################## 
##
## <-- User Input end
##
########################################################## 
dets = [ det for det in dets if checkDet(ds.env(), det.det.alias)]
#for now require all area detectors in run to also be present in event.

defaultDets = defaultDetectors(hutch)
if len(ttCalib)>0:
    setParameter(defaultDets, ttCalib)
if len(aioParams)>0:
    setParameter(defaultDets, aioParams, 'ai')
if len(epicsPV)>0:
    defaultDets.append(epicsDetector(PVlist=epicsPV, name='epicsUser'))
##adding raw timetool traces:
#defaultDets.append(ttRawDetector(env=ds.env()))
##adding wave8 traces:
#defaultDets.append(wave8Detector('Wave8WF'))

#add config data here
userDataCfg={}
for det in dets:
    userDataCfg[det._name] = det.params_as_dict()
    #print userDataCfg[det._name].keys()
    #for k in userDataCfg[det._name].keys():
    #    print k, userDataCfg[det._name][k]
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
    #    cs140_robMax = cs140_rob.evt.dat.max()
    #    epix_vonHamosMax = epix_vonHamos.evt.dat.max()
    #    combDict = {'userValue': cs140_robMax*epix_vonHamosMax}
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

print 'rank %d on %s is finished'%(ds.rank, hostname)
smldata.save()
