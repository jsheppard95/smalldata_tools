# importing generic python modules
import numpy as np
import psana
import time
import argparse
import socket
import os
import RegDB.experiment_info
from smalldata_tools import defaultDetectors,epicsDetector,printMsg,detData,DetObject
from smalldata_tools import checkDet,getCfgOutput,getUserData,getUserEnvData,dropObject
from smalldata_tools import ttRawDetector,wave8Detector,defaultRedisVars,setParameter
########################################################## 
##
## User Input start --> 
##
########################################################## 
##########################################################
# functions for run dependant parameters
##########################################################d
def getROI_jungfrau(run):
    if isinstance(run,basestring):
        run=int(run)
    if run <= 11:
        return  [ [[271,419], [645,748]] ]
    elif run <= 21:
        return  [ [[0,512], [0,1024]] ]
    else:
        return  [ [[0,512], [0,1024]] ]

##########################################################
# run independent parameters 
##########################################################
#aliases for experiment specific PVs go here
#epicsPV = ['slit_s1_hw'] 
epicsPV = []
#fix timetool calibration if necessary
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

jROI = getROI_jungfrau(run)
jungfrauname='jungfrau512k'
have_jungfrau = checkDet(ds.env(), jungfrauname)
if have_jungfrau:
    #create detector object. needs run for calibration data
    #optinally try common mode method 0 (only pedestal subtraction)
    jungfrau = DetObject(jungfrauname ,ds.env(), int(run), common_mode=7)
    jungfrau.addPhotons(ADU_per_photon=8.8, thresADU=0.9, retImg=2)
    jungfrau.saveFull()
    dets.append(jungfrau)

    jungfrauPS = DetObject(jungfrauname ,ds.env(), int(run), common_mode=0, name='jungfrauPS')
    jungfrauPS.addPhotons(ADU_per_photon=8.8, thresADU=0.9, retImg=2)
    jungfrauPS.saveFull()
    dets.append(jungfrauPS)

########################################################## 
##
## <-- User Input end
##
########################################################## 
dets = [ det for det in dets if checkDet(ds.env(), det._srcName)]
#for now require all area detectors in run to also be present in event.

defaultDets = defaultDetectors(hutch)
if len(ttCalib)>0:
    setParameter(defaultDets, ttCalib)
if len(aioParams)>0:
    setParameter(defaultDets, aioParams, 'ai')
if len(epicsPV)>0:
    defaultDets.append(epicsDetector(PVlist=epicsPV, name='epicsUser'))

#add config data here
userDataCfg={}
for det in dets:
    userDataCfg[det._name]=getCfgOutput(det)
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
            det.evt = dropObject()
            det.getData(evt)
            det.processDetector()
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
    #    if jungfrauImg is None:
    #        jungfrauImg = jungfrau.evt.dat.squeeze()
    #    else:
    #        jungfrauImg += jungfrau.evt.dat.squeeze()
    #except:
    #    pass

#
# run 20 has photons.
#

#runsum=smldata.sum(jungfrauImg)
#smldata.save(jungfrauImg=runsum)
smldata.save()
print 'rank %d on %s is finished'%(ds.rank, hostname)
