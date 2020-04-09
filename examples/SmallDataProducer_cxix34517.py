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
    ret_dict['cspad_center'] = [-2832.307533, 1556.632028]
    ret_dict['cspad_dis_to_sam'] = 56.
    ret_dict['Pplane'] = 1
    return ret_dict

##########################################################
# run independent parameters 
##########################################################
#aliases for experiment specific PVs go here
#epicsPV = ['slit_s1_hw'] 
epicsPV = ['pi3_x','pi3_y','pi3_z','pi3_fine_x','pi3_fine_y','pi3_fine_z','DsdCspad_diffraction_intensity']
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
## User Input start --> 
##
########################################################## 
dets=[]

haveDet = checkDet(ds.env(), 'Sc3Inline')
if haveDet:
    common_mode=-1 # raw
    #common_mode=0 # pedSub 
    det = DetObject('Sc3Inline' ,ds.env(), int(run), name='Sc3Inline', common_mode=common_mode)
    det.addFunc(ROIFunc(writeArea=True))
    dets.append(det)


azIntParams = getAzIntParams(run)
haveDet = checkDet(ds.env(), 'DsdCsPad')
if haveDet:
    #common_mode=1 # common_mode
    common_mode=0 # pedSub 
    det = DetObject('DsdCsPad' ,ds.env(), int(run), name='DsdCsPad', common_mode=common_mode)
    det.addFunc(ROIFunc())
    roiFunc = ROIFunc()
    roiFunc.addFunc(projectionFunc(axis=-1))
    det.addFunc(roiFunc)

    center=azIntParams['cspad_center']
    azav_dis_to_sam=azIntParams['cspad_dis_to_sam']
    azav_eBeam=azIntParams['eBeam']
    if center!=[]:
        azav = azimuthalBinning(center=[center[1], center[0]], dis_to_sam=azav_dis_to_sam,  phiBins=1, eBeam=azav_eBeam, Pplane=azIntParams['Pplane'],userMask=edge_mask)
        det.addFunc(azav)

    dets.append(det)

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

##adding wave8 traces:
#defaultDets.append(wave8Detector('Wave8WF'))
##adding raw timetool traces:
#try:
#    defaultDets.append(ttRawDetector(env=ds.env()))
#except:
#    pass

#add config data here
userDataCfg={}
for det in dets:
    userDataCfg[det._name] = det.params_as_dict()
Config={'UserDataCfg':userDataCfg}

eventNr=0
stepNr=-1 #to start counting from 0.
for step in ds.steps():
    stepNr += 1
    for evt in step.events():
        if eventNr >= maxNevt/ds.size:
            break

        eventNr += 1
        smldata.event({'scan':{'stepNr': stepNr}})

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
                #print 'keys: ',userDict[det._name].keys()
                try:
                    envData=getUserEnvData(det)
                    if len(envData.keys())>0:
                        userDict[det._name+'_env']=envData
                except:
                    pass
                #print userDict[det._name]
                #print('data-ROI: ',userDict['epix10ka2m']['full'])
            except:
                pass
        smldata.event(userDict)

        #here you can add any data processing you like, just add a dictionay with the relevant information at the end
        #try:
        #    mydata = epix10k.evt.dat
        #    combDict = {'userValue': np.nanmax(mydata)}
        #    smldata.event(combDict)
        #except:
        #    pass

sumDict={'Sums': {}}
for det in dets:
    for key in det.storeSum().keys():
        sumData=smldata.sum(det.storeSum()[key])
        sumDict['Sums']['%s_%s'%(det._name, key)]=sumData
if len(sumDict['Sums'].keys())>0:
    smldata.save(sumDict)

print 'rank %d on %s is finished'%(ds.rank, hostname)
smldata.save()
