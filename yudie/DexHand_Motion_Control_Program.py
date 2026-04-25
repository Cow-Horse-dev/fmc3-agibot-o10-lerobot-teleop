import time
import argparse
import platform
import sdk_bootstrap
from Data_Receiver import GloveReceiver, ServerStatus
if platform.system() == 'Windows': import msvcrt

def main(): 
    parser = argparse.ArgumentParser(description='DexHand Motion Control Program (DHMC)')
    parser.add_argument('--mode', choices=[
                        'agibotHand_O10',
                        'agibotHand_O12',
                        'brainco_revo1', 
                        'brainco_revo2',
                        'CHOHO',
                        'inspire_RH56DFX', 
                        'inspire_RH56F1E4',
                        'DH116',
                        'linkerhand_O6',
                        'linkerhand_O7', 
                        'linkerhand_L10', 
                        'linkerhand_L20', 
                        'oyhand', 
                        'dexh13',
                        'xhand', 
                        'ryHand_H2',
                        'ryHand_H15',
                        "AeroHand"], 
                        help='Choose robot hand type', default='agibotHand_O10')
    parser.add_argument('--dataType', type=str, choices=['Json','Protobuf','TeleopProtobuf'], help='Data receive type, default is Json. TeleopProtobuf is the protobuf from VR application.', default='Json')
    parser.add_argument('--ip', help='IP address, default is local IP 127.0.0.0', default='127.0.0.1')
    parser.add_argument('--port', type=int, help='Port number, default is 7777', default=7777)
    parser.add_argument('--role', type=str, help='Role name, if cannot find, take first one as default under Json data type, Protobuf needs exact correct role name', default="teleop")
    parser.add_argument('--usb', type=str, help='The USB port of robot hand, on WIN sys the default is COM1, on LINUX sys is /dev/ttyUSB0, for CAN is PCAN_USBBUS1', default='/dev/ttyUSB0')
    parser.add_argument('--hand', type=str, choices=['left', 'right', 'both'], help='Control left, right or both hand(not all hands provide both sample)', default='right')
    parser.add_argument('--canType', choices= ['multiChannel','multiCan'], type=str, help='AGIBOT CAN Control Mode(only work when using agibotHand_O10 or agibotHand_O12)', default='multiChannel')
    args, unknown = parser.parse_known_args()

    # UDP initialize
    sdk = GloveReceiver()
    sdk.server_addr = (args.ip, args.port)
    sdk.initialize(args.dataType, args.role, args.hand)
    if sdk.cur_status != ServerStatus.READY:
        return
    sdk.start_listening()

    #AGIBOT
    if args.mode == 'agibotHand_O10':
        from AGIBOT.Omnihand_o10_yudie import init_hand_Omni_multiCan, init_hand_OmnimultiChannel, is_hand_ready, set_hand_position
        hands = init_hand_OmnimultiChannel(args.hand) if(args.canType == 'multiChannel') else init_hand_Omni_multiCan(args.hand)

        requested_hands = []
        if args.hand in ('left', 'both'):
            requested_hands.append(('left', hands[0]))
        if args.hand in ('right', 'both'):
            requested_hands.append(('right', hands[1]))

        for hand_name, hand in requested_hands:
            if not is_hand_ready(hand):
                print(f"{hand_name} OmniHand initialization failed, program terminated.")
                sdk.end_listening()
                return

        def update():
            if args.hand == 'both':
                set_hand_position(hands[0], sdk.get_hand_data('left'), 'left')
                set_hand_position(hands[1], sdk.get_hand_data('right'), 'right')
            else:
                set_hand_position(hands[0 if args.hand == 'left' else 1], sdk.get_hand_data(args.hand), args.hand)
    if args.mode == 'agibotHand_O12':
        from AGIBOT.Omnihand_o12_yudie import Agibot_HandO12
        hand = Agibot_HandO12(hand_type=args.hand)
        def update(): 
            hand.set_angles(sdk.get_hand_data(args.hand))

    # BrainCo
    if args.mode == 'brainco_revo1':
        from BrainCo.revo1_hand_yudie import init_hand, move_hand
        client, slave_id = init_hand(args.usb, slave_id = 126 if args.hand == 'left' else 127)
        def update():
            move_hand((client, slave_id), sdk.get_hand_data(args.hand))
    if args.mode == 'brainco_revo2':
        from BrainCo.revo2_hand_yudie import init_hand_Revo2, move_hand_Revo2
        client, slave_id = init_hand_Revo2(args.usb, slave_id = 126 if args.hand == 'left' else 127)
        def update():
            move_hand_Revo2(client, slave_id, sdk.get_hand_data(args.hand))

    #CHOHO
    if args.mode == 'CHOHO':
        from CHOHO.CHOHO_yudie import CHOHO
        choho_hand = CHOHO(args.usb)
        def update():
            choho_hand.CHOHO_setPose(sdk.get_hand_data(args.hand))

    # INSPIRE-ROBOTS
    if 'inspire' in args.mode:
        version = args.mode.split("_")[1]
        from INSPIRE_ROBOTS.inspire_hand_yudie import init_hand_inspire, move_hand_inspire
        ser = init_hand_inspire(version, port=args.usb)
        def update():
            move_hand_inspire(version, ser, sdk.get_hand_data(args.hand))

    # Leadshine
    if args.mode == 'DH116':
        from Leadshine.lhandprolib_yudie import init_LHandProLib, run_hand_move
        lhpList = init_LHandProLib(args.hand != 'both')
        for lhp in lhpList:
            if lhp is None or isinstance(lhp, int):
                print("LHandProLib init failed, program terminated.")
                return
        def update():
            if(args.hand == 'both'):
                run_hand_move(lhpList[0], 6, sdk.get_hand_data('left'), 'left')
                run_hand_move(lhpList[1], 6, sdk.get_hand_data('right'), 'right')
            else:
                run_hand_move(lhpList[0], 6, sdk.get_hand_data(args.hand), args.hand)

    # LINKERBOT
    if 'linkerhand' in args.mode:
        from LINKERBOT.linker_hand_yudie import LinkerHandSender
        version = args.mode.split("_")[1]
        if(args.hand == 'both'):
            leftSender = LinkerHandSender(hand_type='left', hand_joint=version, can='PCAN_USBBUS1')
            rightSender = LinkerHandSender(hand_type='right', hand_joint=version, can='PCAN_USBBUS2')
            def update():
                leftSender.send_data(sdk.get_hand_data('left'), version)
                rightSender.send_data(sdk.get_hand_data('right'), version)
        else:
            sender = LinkerHandSender(hand_type=args.hand, hand_joint=version, can=args.usb)
            def update():
                sender.send_data(sdk.get_hand_data(args.hand), version)
    
    # OYMotion
    if args.mode == 'oyhand':
        from OYMotion.OY_hand_yudie import OYHandSender
        hand = OYHandSender()
        if hand.connect():
            print("connect hand ok.")
        def update():
            try:
                hand.write_registers(sdk.get_hand_data(args.hand))
            except Exception as e:
                print(f"Error: {e}")
    
    #PaXini
    if args.mode == 'dexh13':
        from PaXini.dexh13_hand_yudie import DexH13Example
        dexh13_example = DexH13Example(handy_port_num=args.usb, camera_port_num="/dev/video0")
        dexh13_example.init_hand()
        def update():
            dexh13_example.set_joint_radian(sdk.get_hand_data(args.hand))

    # ROBOTERA
    if args.mode == 'xhand':
        from ROBOTERA.xhand_control_yudie import XHandControlExample, xhand_ready
        xhand_exam = XHandControlExample(hand_id=0, position=0.1, mode=3)
        xhand_ready(xhand_exam, port=args.usb)
        def update():
            XHandControlExample.run_yudie(xhand_exam, sdk.get_hand_data(args.hand))
    
    #RUIYAN
    if 'ryHand' in args.mode:
        version = args.mode.split("_")[1]
        from RUIYAN.ryhand_yudie import RyHandSender
        hand = RyHandSender()
        def update():
            if(version == 'H2'):
                hand.update_motor_positions_H2(sdk.get_hand_data(args.hand), 0 if args.hand == 'left' else 1)
            else:
                hand.update_motor_positions_H15(sdk.get_hand_data(args.hand), 0 if args.hand == 'left' else 1)

    #TetherIA
    if args.mode == 'AeroHand':
        from TetherIA.Aerohand_yudie import Aerohand
        aeroHand = Aerohand(args.usb)
        def update():
            aeroHand.set_Joint_positions(sdk.get_hand_data(args.hand))

    while True:
        try:
            if sdk.get_data_valid():
                update()
            if platform.system() == 'Windows' and msvcrt.kbhit():
                key = msvcrt.getch()
                if key == b'\x1b':  # ESC key
                    sdk.end_listening()
                    break
            time.sleep(0.05)
        except KeyboardInterrupt:
            sdk.end_listening()
            break
    print("DexHand Motion Control Program is terminated.\n")

if __name__ == "__main__":
    main()
