# importing generic python modules
import numpy as np
import psana
import time
import argparse
import socket
import os
import RegDB.experiment_info

import sys
sys.path.append('/reg/g/xpp/xppcode/python/smalldata_tools/')

from smalldata_tools import defaultDetectors,epicsDetector,printMsg,detData,DetObject
from smalldata_tools import checkDet,getCfgOutput,getUserData,getUserEnvData,dropObject

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
    lastRun = RegDB.experiment_info.experiment_runs(hutch)[-1]['num'] 
    if (run < lastRun) or (run == lastRun and (RegDB.experiment_info.experiment_runs(hutch)[-1]['end_time_unix'] is not None)):
        xtcdirname = '/reg/d/ffb/%s/%s/xtc'%(hutch.lower(),expname)
        xtcname=xtcdirname+'/e*-r%04d-*'%int(run)
        import glob
        presentXtc=glob.glob('%s'%xtcname)
        if len(presentXtc)==0:
            dsname='exp='+expname+':run='+run+':smd'
else:
    expname=args.exp
    hutch=expname[0:3].upper()
    expnameCurr=RegDB.experiment_info.active_experiment(hutch)[1]
    dsname='exp='+expname+':run='+run+':smd'
    if expnameCurr == expname:
        dsname='exp='+expname+':run='+run+':smd'
        lastRun = RegDB.experiment_info.experiment_runs(hutch)[-1]['num'] 
        if (int(run) < int(lastRun)) or (int(run) == int(lastRun) and (RegDB.experiment_info.experiment_runs(hutch)[-1]['end_time_unix'] is not None)):
            xtcdirname = '/reg/d/ffb/%s/%s/xtc'%(hutch.lower(),expname)
            xtcname=xtcdirname+'/e*-r%04d-*'%int(run)
            import glob
            presentXtc=glob.glob('%s'%xtcname)
            if len(presentXtc)>0:
                dsname='%s:dir=/reg/d/ffb/%s/%s/xtc'%(dsnam,hutch.lower(),expname)
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

#for this, never wait for recorder streams....
#if args.norecorder:
#    dsname=dsname+':stream=0-79'
dsname=dsname+':stream=0-79'

debug = True
time_ev_sum = 0.
try:
    ds = psana.MPIDataSource(dsname)
except:
    import sys
    sys.exit()

try:    
    if dirname is None:
        #dirname = '/reg/d/psdm/%s/%s/hdf5/smalldata'%(hutch.lower(),expname)
        dirname = '/reg/d/psdm/%s/%s/results/arphdf5'%(hutch.lower(),expname)
    directory = os.path.dirname(dirname)
    #I think this is not actually working. Can't do it from script. Need to create first.
    if ds.rank==0 and not os.path.isdir(dirname):
        print 'made directory for output files: %s'%dirname
        os.mkdir(directory)

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

defaultDets = defaultDetectors(hutch)
epicsPV=[] #automatically read PVs from questionnaire/epicsArch file 
if len(epicsPV)>0:
    defaultDets.append(epicsDetector(PVlist=epicsPV, name='epicsUser'))

print 'DEBUG: now start event loop'
for eventNr,evt in enumerate(ds.events()):
    printMsg(eventNr, evt.run(), ds.rank, ds.size)

    if eventNr >= maxNevt/ds.size:
        break

    #add default data
    defData = detData(defaultDets, evt)
    #for key in defData.keys():
    #    print eventNr, key, defData[key]
    smldata.event(defData)

print 'rank %d on %s is finished'%(ds.rank, hostname)
smldata.save()
