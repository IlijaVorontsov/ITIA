from opcua import Client, ua
from time import sleep
from random import randint
import paho.mqtt.client as paho


mqtt_client = paho.Client()
mqtt_client.connect("128.130.56.9", 49152)

def mqtt_publish(topic: str, value: int) -> None:
    mqtt_client.publish(topic, f"{value}")



url_target1 = "opc.tcp://192.168.162.33:4840"
url_target2 = "opc.tcp://192.168.162.49:4840"
url_target3 = "opc.tcp://192.168.162.65:4840"
url_namespace = "http://itia-target"


class Workpiece:
    materialOf = {
        1: "Red",
        2: "Black",
        3: "Aluminum"
    }
    def __init__(self, material: int, heightInBound: bool):
        self.height = heightInBound # Always True
        self.slide = material + 1
        self.material = self.materialOf[material]
        

class Target:
    states = {
        0: "Reset",
        1: "Error",
        2: "Waiting",
        3: "Run"
    }
    old_stateR = "Reset"
    old_stateL = "Reset"
    error_distributed = False
    uptime = 0
    def __init__(self, url: str, namespace: str, number: int):
        self.client = Client(url=url)
        self.namespace = namespace
        self.number = number
        self.stationL = f"Station{number*2-1}"
        self.stationR = f"Station{number*2}"

    def run(self):
        self.client.connect()
        self.idx = self.client.get_namespace_index(self.namespace)
        self.target = self.client.nodes.root.get_child(["0:Objects", f"{self.idx}:Targets", f"{self.idx}:Target {self.number}"])
        self.control = self.target.get_child([f"{self.idx}:Control"])
        self.stateL = self.states[self.client.get_node(self.target.get_child([f"{self.idx}:Station {self.number*2-1}", f"{self.idx}:State"])).get_value()]
        self.stateR = self.states[self.client.get_node(self.target.get_child([f"{self.idx}:Station {self.number*2}", f"{self.idx}:State"])).get_value()]
        self.setError = lambda: self.control.call_method(f"{self.idx}:Error")
        self.setStartup = lambda: self.control.call_method(f"{self.idx}:Startup")
        
        self.errorHandling()

        if self.stateL == "Reset" or self.stateR == "Reset":
            self.setStartup()
            mqtt_publish(f"itia/{self.stationL}/events/startup", 1)
            mqtt_publish(f"itia/{self.stationR}/events/startup", 1)

        self.uptime += 1
        mqtt_publish(f"itia/{self.stationL}/events/uptime", self.uptime)
        mqtt_publish(f"itia/{self.stationR}/events/uptime", self.uptime)

            
    def errorHandling(self):
        global distribute_error

        if (self.old_stateL != "Error" and self.stateL == "Error"):
            print(f"Target {self.number}, Station {self.number*2-1}: Error")
            mqtt_publish(f"itia/{self.stationL}/events/error", 1)
            distribute_error = True
            self.error_distributed = False
        elif (self.stateL != "Error" and self.old_stateL == "Error"):
            print(f"Target {self.number}, Station {self.number*2-1}: Error resolved")
            mqtt_publish(f"itia/{self.stationL}/events/error", 0)
            distribute_error = False
            self.error_distributed = False

        if (self.old_stateR != "Error" and self.stateR == "Error"):
            print(f"Target {self.number}, Station {self.number*2}: Error")
            mqtt_publish(f"itia/{self.stationR}/events/error", 1)
            distribute_error = True
            self.error_distributed = False
        elif (self.stateR != "Error" and self.old_stateR == "Error"):
            print(f"Target {self.number}, Station {self.number*2}: Error resolved")
            mqtt_publish(f"itia/{self.stationR}/events/error", 0)
            distribute_error = False
            self.error_distributed = False

        if distribute_error and not self.error_distributed:
            self.setError()
            self.error_distributed = True



class Target1(Target):
    def __init__(self):
        super().__init__(url_target1, url_namespace, 1)
        self.old_magaizneEmpty = False


    def run(self):
        super().run()
        self.magazineEmpty = self.client.get_node(self.control.get_child([f"{self.idx}:MagazineEmpty"])).get_value()
        self.readyToTransfer = self.client.get_node(self.control.get_child([f"{self.idx}:ReadyToTransfer"])).get_value()
        self.workpieceProperties = self.control.get_child([f"{self.idx}:WorkpieceProperties"])
        self.workpieceMaterial = self.client.get_node(self.workpieceProperties.get_child([f"{self.idx}:WorkpieceMaterial"])).get_value()
        self.heightInBound = self.client.get_node(self.workpieceProperties.get_child([f"{self.idx}:HeightInBound"])).get_value()
        self.workpiecePassed = self.client.get_node(self.control.get_child([f"{self.idx}:WorkpiecePassed"])).get_value()    #MM


        global workpiecePassed  #MM
        workpiecePassed = self.workpiecePassed

        self.ejectFromMagazine = lambda: self.control.call_method(f"{self.idx}:EjectFromMagazine")
        self.transferWorkpiece = lambda: self.control.call_method(f"{self.idx}:TransferWorkpiece")

        if not self.magazineEmpty:
            # print("Target 1: Ejecting from magazine")
            self.ejectFromMagazine()
        elif not self.old_magaizneEmpty and self.magazineEmpty:
            print("Target 1: Magazine empty")
            mqtt_publish(f"itia/{self.stationL}/events/magazineEmpty", 1)
        elif self.old_magaizneEmpty and not self.magazineEmpty:
            print("Target 1: Magazine refilled")
            mqtt_publish(f"itia/{self.stationL}/events/magazineEmpty", 0)

        global target2_ReadyToReceive, target12_transfered_Workpiece, transferRequested

        if self.readyToTransfer:
            transferRequested = True

        # print(f"Target 1: Ready to transfer: {self.readyToTransfer}, Workpiece passed: {self.workpiecePassed}, Target 2 ready to receive: {target2_ReadyToReceive}, Turntable ready: {turntableReady}, Workpiece transfered: {target12_transfered_Workpiece != None}")

        if self.readyToTransfer and target2_ReadyToReceive and turntableReady and target12_transfered_Workpiece == None:   #MM: turntable
            target12_transfered_Workpiece = Workpiece(self.workpieceMaterial+1, self.heightInBound)
            print(f"Target 1: Transfering workpiece {target12_transfered_Workpiece.material}")
            mqtt_publish(f"itia/{self.stationR}/events/transfer", target12_transfered_Workpiece.slide)
            self.transferWorkpiece()
            workpiecePassed = False  #MM
        

        self.old_stateL = self.stateL
        self.old_stateR = self.stateR
        self.old_magaizneEmpty = self.magazineEmpty

        self.client.disconnect()

class Target2(Target):
    # State: DoAction and RotateTurntable
    state = "RotateTurntable"
    lost = 0
    received = 0
    ejected = 0
    def __init__(self):
        super().__init__(url_target2, url_namespace, 2)
        self.lastColor = 0
        self.target12_transfered_Workpiece = None##MM

    def run(self):
        super().run()
        global target2_ReadyToReceive, target2_Workpieces, target12_transfered_Workpiece, target2_swivelArmReady, distribute_error

        self.holeChecked = self.client.get_node(self.control.get_child([f"{self.idx}:HoleChecked"])).get_value()
        self.turntableReady = self.client.get_node(self.control.get_child([f"{self.idx}:TurntableReady"])).get_value()
        target2_swivelArmReady = self.swifelArmReady = self.client.get_node(self.control.get_child([f"{self.idx}:SwivelArmReady"])).get_value()
        self.readyToReceive = self.client.get_node(self.control.get_child([f"{self.idx}:readyToReceive"])).get_value()
        
        self.transferWorkpiece = lambda b: self.control.call_method(f"{self.idx}:TransferWorkpiece", ua.Variant(b, ua.VariantType.Boolean))
        self.turnTurntable = lambda: self.control.call_method(f"{self.idx}:Turntable")
        self.drill = lambda: self.control.call_method(f"{self.idx}:Drill")
        self.checkHole = lambda: self.control.call_method(f"{self.idx}:CheckHole")
         
        target2_ReadyToReceive = self.readyToReceive

        global turntableReady
        turntableReady = self.turntableReady

        # print all Variables
        # print(f"Target 2: HoleChecked: {self.holeChecked}, TurntableReady: {self.turntableReady}, SwifelArmReady: {self.swifelArmReady}, ReadyToReceive: {self.readyToReceive}")
        # print state of target
        # print(f"Target 2: State: {self.state}")
        
        
        #target12_transfered_Workpiece = Workpiece(self.lastColor+1, True) # Testing code since target 1 didn't work
        global workpiecePassed, transferRequested, distribute_error
        if workpiecePassed:  #MM
            
            if target12_transfered_Workpiece != None and self.readyToReceive:
                print("Target 2: Error lost in transfer")
                self.lost += 1
                mqtt_publish(f"itia/{self.stationL}/errors/lost", self.lost)
                distribute_error = True
                self.setError()
            elif target12_transfered_Workpiece != None and not self.readyToReceive:# and self.turntableReady: MM
                transferRequested = False
                print("Target 2: Received workpiece")
                self.received += 1
                mqtt_publish(f"itia/{self.stationL}/events/received", self.received)
                #if len(target2_Workpieces) <= 2:
                target2_Workpieces.append(target12_transfered_Workpiece)
                target12_transfered_Workpiece = None
                
                #self.lastColor = (self.lastColor + 1) % 3 # Testing code since target 1 didn't work
                
        
        # print queue of workpieces
        '''
        for i in range(len(target2_Workpieces)):
            if target2_Workpieces[i] != None:
                print(f"Target 2: Workpiece {i}: {target2_Workpieces[i]}")
            else:
                print(f"Target 2: Workpiece {i}: None")
        '''
        
        global target3_ReadyToReceive, target3_Workpieces
        #print(f"Target 2: Target 3: ReadyToReceive: {target3_ReadyToReceive}")
        target2_readyToTransfer = target2_Workpieces[0] != None
        # if only None in list, then don't turn
        if self.turntableReady and not all(x == None for x in target2_Workpieces) and not (target2_readyToTransfer and not target3_ReadyToReceive) and not transferRequested:    ##MM Last condition
            if self.state == "DoAction" and (not target2_Workpieces[0] != None or self.swifelArmReady):
                if target2_Workpieces[2] != None: # Drill position occupied
                    self.drill()
                if target2_Workpieces[1] != None: # Check whole position
                    self.checkHole()
                if target2_Workpieces[0] != None: # Transfer position occupied
                    # Ejecting 1 out of 10 at random
                    if self.holeChecked and randint(0, 9) == 0:
                        print("Target 2: Ejecting workpiece")
                        self.ejected += 1
                        mqtt_publish(f"itia/{self.stationL}/events/ejected", self.ejected)
                        self.transferWorkpiece(False)
                        target2_Workpieces.pop(0)
                    else:
                        self.transferWorkpiece(True)
                        workpiece = target2_Workpieces.pop(0)
                        print(f"Target 2: Workpiece transferred [Material: {workpiece.material}, Height: {workpiece.height}]")
                        mqtt_publish(f"itia/{self.stationL}/events/transfered", workpiece.slide)
                        global target23_transfered_Workpiece
                        target23_transfered_Workpiece = workpiece
                        target2_swivelArmReady = False
                else:
                    target2_Workpieces.pop(0)
                self.state = "RotateTurntable"

            elif self.state == "RotateTurntable":
                print("Target 2: Turning turntable")
                mqtt_publish(f"itia/{self.stationL}/events/turning", 1)
                if len(target2_Workpieces) <= 2: # No workpiece transferred
                    target2_Workpieces.append(None)
                self.turnTurntable()
                self.state = "DoAction"
                turntableReady = False

            

        self.old_stateL = self.stateL
        self.old_stateR = self.stateR

        self.client.disconnect()

class Target3(Target):
    received = 0
    lost = 0
    def __init__(self):
        super().__init__(url_target3, url_namespace, 3)
        self.old_someSlideFull = False
        self.lastSlide = 0
        

    def run(self):
        super().run()
        global target3_ReadyToReceive
        target3_ReadyToReceive = self.readyToReceive = self.client.get_node(self.control.get_child([f"{self.idx}:ReadyToReceive"])).get_value()
        self.someSlideFull = self.client.get_node(self.control.get_child([f"{self.idx}:SomeSlideFull"])).get_value()
        self.workpieceInBuffer = self.client.get_node(self.control.get_child([f"{self.idx}:WorkpieceInBuffer"])).get_value()
        self.workpieceReceived = self.client.get_node(self.control.get_child([f"{self.idx}:WorkpieceReceived"])).get_value()

        self.passWorkpieceToSlide = lambda slide: self.control.call_method(f"{self.idx}:PassWorkpieceToSlide", ua.Variant(slide, ua.VariantType.Byte))
        self.setSignalTower = lambda red, yellow, green: self.control.call_method(f"{self.idx}:SetSignalTower", ua.Variant(red, ua.VariantType.Boolean), ua.Variant(yellow, ua.VariantType.Boolean), ua.Variant(green, ua.VariantType.Boolean))

        global target23_transfered_Workpiece, target2_swivelArmReady, distribute_error

        if target23_transfered_Workpiece != None:
            if self.workpieceReceived:
                print("Target 3: Received workpiece")
                self.received += 1
                mqtt_publish(f"itia/{self.stationL}/events/received", self.received)
                target3_Workpieces.append(target23_transfered_Workpiece)
                target23_transfered_Workpiece = None
                self.client.get_node(self.control.get_child([f"{self.idx}:WorkpieceReceived"])).set_attribute(ua.AttributeIds.Value, ua.DataValue(ua.Variant(False, ua.VariantType.Boolean)))
            elif target2_swivelArmReady:
                print("Target 3: Error lost in transfer")
                self.lost += 1
                mqtt_publish(f"itia/{self.stationL}/errors/lost", self.lost)
                distribute_error = True
                self.setError()
                target23_transfered_Workpiece = None
        
        if self.stateL == "Error" or self.stateR == "Error":
            self.setSignalTower(True, False, False)
        elif self.someSlideFull:
            self.setSignalTower(False, True, False)
            
        else:
            self.setSignalTower(False, False, True)

        if self.someSlideFull and not self.old_someSlideFull:
            mqtt_publish(f"itia/{self.stationL}/events/slide_full", 1)
        elif not self.someSlideFull and self.old_someSlideFull:
            print("Target 3: Workpieces removed from slide")
            mqtt_publish(f"itia/{self.stationL}/events/slide_full", 0)
        
        if self.workpieceInBuffer and len(target3_Workpieces) == 0:
            print("Target 3: ERROR: Workpiece in buffer but no workpiece in list")
            mqtt_publish(f"itia/{self.stationL}/errors/UnknownWorkpiece", 1)
            self.setError()
            self.distribute_error = True

        if self.workpieceInBuffer and not self.someSlideFull and len(target3_Workpieces) > 0:
            slide = target3_Workpieces.pop(0).slide
            print(f"Target 3: Passing workpiece to slide {slide}")
            mqtt_publish(f"itia/{self.stationR}/events/passing", slide)
            self.passWorkpieceToSlide(slide)
            self.lastSlide = slide

        self.old_stateL = self.stateL
        self.old_stateR = self.stateR
        self.old_someSlideFull = self.someSlideFull

        self.client.disconnect()


if __name__ == "__main__":
    global distribute_error
    distribute_error = False

    global workpiecePassed, transferRequested
    workpiecePassed = False
    transferRequested = False

    global target2_ReadyToReceive, target2_Workpieces, target12_transfered_Workpiece, target2_swivelArmReady
    target2_ReadyToReceive = False
    target2_Workpieces = [None, None]
    target12_transfered_Workpiece = None


    global target3_ReadyToReceive, target3_Workpieces, target23_transfered_Workpiece
    target3_ReadyToReceive = False
    target3_Workpieces = []
    target23_transfered_Workpiece = None

    target1 = Target1()
    target2 = Target2()
    target3 = Target3()

    while True:
        try:
            target3.run()
            target2.run()
            target1.run()
        except KeyboardInterrupt:
            mqtt_client.disconnect()
            Target1.client.disconnect()
            Target2.client.disconnect()
            Target3.client.disconnect()
        finally:
            sleep(2)

    