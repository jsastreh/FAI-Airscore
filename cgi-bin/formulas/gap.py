'''
standard gap formulas.
 TODO will need it's own version of formulas in pwc in order to be used for gap scoring

'''

from myconn import Database

def task_totals(task, formula):
    '''
    This new version uses a view to collect task totals.
    It means we do not need to store totals in task table anylonger,
    as they are calculated on runtime from mySQL using all task results
    '''

    tasPk = task.tasPk
    launchvalid = task.launchvalid
    mindist = formula['forMinDistance']
    glidebonus = 0
    landed = 0
    tqtime = None


    #todo: 'Landed' misses people who made ESS but actually landed before goal
    query ="""  SELECT
                    `TotalPilots`,
                    `TotalDistance`,
                    `TotDistOverMin`,
                    `TotalLaunched`,
                    `Deviation`,
                    `TotalLanded`,
                    `TotalESS`,
                    `TotalGoal`,
                    `maxDist`,
                    `firstStart`,
                    `lastStart`,
                    `firstSS`,
                    `lastSS`,
                    `firstESS`,
                    `lastESS`,
                    `minTime`,
                    `minTimeGoal`,
                    `LCmin`
                FROM
                    `TaskTotalsView`
                WHERE
                    `tasPk` = %s
                LIMIT 1"""
    params = [tasPk]
    with Database() as db:
        # get the formula details.
        t = db.fetchone(query, params)

    if not t:
        print(query)
        print('No rows in TaskTotalsView for task ', tasPk)
        return

    task.stats['distance']      = t['TotalDistance']
    task.stats['launched']      = int(t['TotalLaunched'])
    task.stats['pilots']        = int(t['TotalPilots'])     # pilots present on take-off, ABS are not counted
    task.stats['stddev']        = t['Deviation']
    task.stats['distovermin']   = t['TotDistOverMin']
    task.stats['ess']           = int(t['TotalESS'])
    task.stats['goal']          = int(t['TotalGoal'])
    task.stats['maxdist']       = t['maxDist']
    task.stats['fastest']       = t['minTime']
    task.stats['fastestingoal'] = t['minTimeGoal']
    task.stats['minarr']        = t['firstESS']
    task.stats['maxarr']        = t['lastESS']
    #task.stats['tqtime']        = t['minTime'] # ???
    #task.stats['LCmin']         = t['LCmin']   # not already calculated
    task.stats['mindept']       = t['firstStart']
    task.stats['lastdept']      = t['lastStart']

    if task.stopped_time:     # Null is returned as None
        glidebonus = formula['glidebonus']
        print("F: glidebonus=", glidebonus)
        task.stats['landed'] = t['TotalLanded']

    return task.stats

def launch_validity(taskt, formula):
    '''
    9.1 Launch Validity
    ‘Pilots Present’ are pilots arriving on take-off, with their gear, with the intention of flying.
    For scoring purposes, ‘Pilots Present’ are all pilots not in the ‘Absent’ status (ABS):
    Pilots who took off, plus pilots present who did not fly (DNF). DNFs need to be attributed carefully.
    A pilot who does not launch due to illness, for instance, is not a DNF, but an ABS.

    LVR = min (1, num_pilots_flying / (pilots_present * nom_launch) )
    Launch Validity = 0.027*LRV + 2.917*LVR^2 - 1.944*LVR^3
    ?? Setting Nominal Launch = 10 (max number of DNF that still permit full validity) ??
    '''

    LVR = min(1, (taskt['launched']) / (taskt['pilots'] * formula['forNomLaunch']))
    launch = 0.028 * LVR + 2.917 * LVR**2 - 1.944 * LVR**3
    launch = min(launch, 1) if launch > 0 else 0           #sanity
    print("GAP Launch validity = launch")

    return launch

def distance_validity(taskt, formula):
    '''
    9.2 Distance Validity
    NomDistArea = ( ((NomGoal + 1) * (NomDist − MinDist)) + max(0, (NomGoal * BestDistOverNom)) ) / 2
    DVR = SumOfFlownDistancesOverMinDist / (NumPilotsFlying * NomDistArea)
    Dist. Validity = min (1, DVR)
    '''

    nomgoal         = formula['forNomGoal']         # nom goal percentage
    nomdist         = formula['forNomDistance']     # nom distance
    mindist         = formula['forMinDistance']     # min distance
    totalflown      = taskt['distovermin']          # total distance flown by pilots over min. distance
    BestDistOverNom = taskt['maxdist'] - nomdist    # best distance flown ove minimum dist.
    # bestdistovermin = taskt['maxdist'] - mindist  # best distance flown ove minimum dist.
    NumPilotsFlying = taskt['launched']             # Num Pilots flown

    NomDistArea     = ( ((nomgoal + 1)*(nomdist - mindist)) + max(0, (nomgoal * BestDistOverNom)) ) / 2
    DVR             = totalflown / (NumPilotsFlying * NomDistArea)

    print("Nom. Goal: {}% | Min. Distance: {} Km | Nom. Distance: {} Km".format(nomgoal*100, mindist/1000, nomdist/1000))
    print("Total Flown Distance over min. dist.: {} Km".format(totalflown/1000))
    print("Pilots launched: {} | Best Distance over Nom.: {} Km".format(NumPilotsFlying, BestDistOverNom/1000))
    print("NomDistArea: {}".format(NomDistArea))
    print('DVR = {}'.format(DVR))

    distance        = min(1, DVR)

    print("Distance validity = {}".format(distance))
    return distance

def time_validity(taskt, formula):
    '''
    9.3 Time Validity
    Time validity depends on the fastest time to complete the speed section, in relation to nominal time.
    If the fastest time to complete the speed section is longer than nominal time, then time validity is always equal to 1.
    If no pilot finishes the speed section, then time validity is not based on time but on distance:

    If one pilot reached ESS: TVR = min(1, BestTime / NominalTime)
    If no pilot reached ESS: TVR = min(1, BestDistance / NominalDistance)

    TimeVal = max(0, min(1, -0.271 + 2.912*TVR - 2.098*TVR^2 + 0.457*TVR^3))
    '''

    if taskt['ess'] > 0:
        TVR = min(1, (taskt['fastest'] / formula['forNomTime']))
        print("ess > 0, TVR = {}".format(TVR))
    else:
        TVR = min(1, (taskt['maxdist'] / formula['forNomDistance']))
        print("none in goal, TVR = {}".format(TVR))

    time = max(0, min(1, (-0.271 + 2.912 * TVR - 2.098 * TVR**2 + 0.457 * TVR**3)))

    print("Time validity = {}".format(time))
    return time

def stopped_validity(task, formula):
    '''
    12.3.3 Stopped Task Validity
    NumberOfPilotsReachedESS > 0 : StoppedTaskValidity = 1
    NumberOfPilotsReachedESS = 0 :
    StoppedTaskValidity = min(1, sqrt((bestDistFlown - avgDistFlown)/(TaskDistToESS-bestDistFlown+1)*sqrt(stDevDistFlown/5))+(pilotsLandedBeforeStop/pilotsLaunched)^3)
    '''
    from math import sqrt

    taskt = task.stats

    if taskt['fastest'] and taskt['fastest'] > 0:
        return 1

    avgdist = taskt['distance'] / taskt['launched']
    distlaunchtoess = task.EndSSDistance

    stopv = min(1,
                (sqrt((taskt['maxdist'] - avgdist) / (distlaunchtoess - taskt['maxdist'] + 1) * sqrt(taskt['stddev'] / 5) )
                + (taskt['landed'] / taskt['launched'])**3))
    return stopv

def day_quality(task, formula):

    if not task.launchvalid:
        print("Launch invalid - dist quality set to 0")
        launch      = 0
        distance    = 0
        time        = 0
        return (distance, time, launch)

    taskt = task.stats

    if taskt['pilots'] == 0:
        launch      = 0
        distance    = 0
        time        = 0.1
        return (distance, time, launch)

    stopv = 1
    if task.stopped_time:
        stopv   = stopped_validity(task, formula)

    launch      = launch_validity(taskt, formula)
    distance    = distance_validity(taskt, formula)
    time        = time_validity(taskt, formula)

    return distance, time, launch, stopv

def points_weight(task, formula):
    from math import sqrt

    taskt = task.stats

    quality = taskt['quality']
    x = taskt['goal'] / taskt['launched']  # GoalRatio

    '''
    DistWeight = 0.9 - 1.665* goalRatio + 1.713*GolalRatio^2 - 0.587*goalRatio^3
    '''
    distweight = 0.9 - 1.665 * x + 1.713 * x * x - 0.587 * x *x *x
    print("PWC 2016 Points Allocatiom distWeight = ", distweight)
    # distweight = 1 - 0.8 * sqrt(x)
    # print("NOT Using 2016 Points Allocatiom distWeight = ", distweight)

    '''
    LeadingWeight = (1 - DistWeight)/8 * 1.4
    '''
    leadweight = (1 - distweight) / 8 * 1.4
    print("LeadingWeight = ", leadweight)
    Adistance = 1000 * quality * distweight  # AvailDistPoints
    print("Available Dist Points = ", Adistance)
    Astart = 1000 * quality * leadweight  # AvailLeadPoints
    print("Available Lead Points = ", Astart)

    '''calculating speedweight and Aspeed using PWC2016 formula, without arrivalweight'''
    # we could safely delete everything concerning Arrival Points in PWC GAP.
    Aarrival = 0
    speedweight = 1 - distweight - leadweight
    Aspeed = 1000 * quality * speedweight  # AvailSpeedPoints
    print("Available Speed Points = ", Aspeed)
    print("points_weight: (", formula['forVersion'], ") Adist=" , Adistance, ", Aspeed=", Aspeed, ", Astart=", Astart ,", Aarrival=", Aarrival)
    return Adistance, Aspeed, Astart, Aarrival


def pilot_departure_leadout(task, pil, Astart):
    from math import sqrt

    taskt = task.stats
    # C.6.3 Leading Points

    LCmin = taskt['LCmin']  # min(tarLeadingCoeff2) as LCmin : is PWC's LCmin?
    LCp = pil['LC']  # Leadout coefficient

    # Pilot departure score
    Pdepart = 0
    '''Departure Points type = Leading Points'''
    if task.departure == 'leadout':  # In PWC is always the case, we can ignore else cases
        print("  - PWC  leadout: LC ", LCp, ", LCMin : ", LCmin)
        if LCp > 0:
            if LCp <= LCmin:
                print("======= being LCp <= LCmin  =========")
                Pdepart = Astart
            elif LCmin <= 0:
                # this shouldn't happen
                print("=======  being LCmin <= 0   =========")
                Pdepart = 0
            else: # We should have ONLY this case
                # $Pdepart = $Astart * (1-(($LCp-$LCmin)*($LCp-$LCmin)/sqrt($LCmin))**(1/3))
                # $Pdepart = $Alead * (1-(($LCp-$LCmin)*($LCp-$LCmin)/sqrt($LCmin))**(1/3)) # Why $Alead is not working?

                # LeadingFactor = max (0, 1 - ( (LCp -LCmin) / sqrt(LCmin) )^(2/3))
                # LeadingPoints = LeadingFactor * AvailLeadPoints
                LF = 1 - ( (LCp - LCmin) ** 2 / sqrt(LCmin) ) ** (1 / 3)
                print("LeadFactor = ", LF)
                if LF > 0:
                    Pdepart = Astart * LF
                    print("=======  Normal Pdepart   =========")

        print("======= PDepart = {}  =========".format(Pdepart))

    # Sanity
    if 0 + Pdepart != Pdepart:
        Pdepart = 0


    if Pdepart < 0:
        Pdepart = 0


    print("    Pdepart: ", Pdepart)
    return Pdepart


def pilot_speed(task, pil, Aspeed):
    from math import sqrt

    taskt = task.stats

    # C.6.2 Time Points
    Tmin = taskt['fastest']
    Pspeed = 0
    Ptime = 0

    if pil['goal'] and Tmin > 0:    # checking that task has pilots in ESS, and that pilot is in ESS
                                    # we need to change this! It works correctly only if Time Pts is 0 when pil not in goal
                                    # for HG we need a fastest and a fastest in goal in TaskTotalsView
        Ptime = pil['time']
        SF = 1 - ((Ptime-Tmin) / 3600 / sqrt(Tmin / 3600) ) ** (5 / 6)

        if SF > 0:
            Pspeed = Aspeed * SF


    print(pil['traPk'], " Ptime: {}, Tmin={}".format(Ptime, Tmin))

    return Pspeed


def pilot_distance(task, pil, Adistance):
    """

    :type pil: object
    """

    maxdist = task.stats['maxdist']
    Pdist = Adistance * pil['distance']/maxdist

    return Pdist
