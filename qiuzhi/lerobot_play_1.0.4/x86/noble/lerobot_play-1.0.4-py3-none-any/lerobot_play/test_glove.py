from .utils.HandDriver_Linux_Py_Angle import UDEGloveSDK

finger_names = ["Thumb1_1", "Thumb1_3", "Index1", "Middle1", "Ring1", "Pinky1"]
finger_dict = {
    "Thumb1_1": (10, -60),
    "Thumb1_3": (0, -60),
    "Index1": (0, -80),
    "Middle1": (0, -80),
    "Ring1": (0, -80),
    "Pinky1": (0, -80),
}

finger_filtering_factor = {
    "Thumb1_1": [0, 250.0, 350.0, 450.0, 550.0, 650.0, 750.0],
    "Thumb1_3": [0, 350.0, 450.0, 550.0, 650.0, 750.0, 850.0],
    "Index1": [
        0,
        200.0,
        250,
        300.0,
        350,
        400.0,
        450,
        500.0,
        550,
        600.0,
        650,
        700.0,
        750,
        800.0,
        850,
        900.0,
    ],
    "Middle1": [
        0,
        200.0,
        250,
        300.0,
        350,
        400.0,
        450,
        500.0,
        550,
        600.0,
        650,
        700.0,
        750,
        800.0,
        850,
        900.0,
    ],
    "Ring1": [
        0,
        200.0,
        250,
        300.0,
        350,
        400.0,
        450,
        500.0,
        550,
        600.0,
        650,
        700.0,
        750,
        800.0,
        850,
        900.0,
    ],
    "Pinky1": [
        0,
        250,
        300.0,
        350,
        400.0,
        450,
        500.0,
        550,
        600.0,
        650,
        700.0,
        750,
        800.0,
        850,
        900.0,
    ],
}


def filtering(finger_name, command):
    """
    根据command的值，查找其在finger_filtering_factor[i]中所在的区间。
    若找到区间 [j, j+1)，则返回 finger_filtering_factor[i][j]。
    若未找到任何匹配区间，则返回 max_val。

    Args:
        finger_name: 索引，指定使用finger_filtering_factor中的哪一行列表
        command: 要判断的输入值

    Returns:
        float: 计算结果
    """
    max_val = 1000  # max_val: 手的最大限位

    # 获取当前要用于判断的因子列表
    factors = finger_filtering_factor[finger_name]

    # 遍历因子列表，寻找command所在的区间
    for j in range(len(factors) - 1):  # 注意范围，因为要取 j 和 j+1
        lower_bound = factors[j]
        upper_bound = factors[j + 1]
        # 若command在 [lower_bound, upper_bound) 区间内，则返回lower_bound
        if lower_bound <= command < upper_bound:
            return lower_bound

    # 如果上面的循环没有找到任何匹配的区间，则执行下面的语句
    return max_val


# 映射函数
def map_angle_to_value(finger_name, current_angle):
    """
    将指定手指的当前角度映射到0-1000的数值范围。

    参数:
        finger_name (str): 手指名称，必须是finger_dict中的键，如'thumb', 'index'等。
        current_angle (float): 该手指的当前角度。

    返回:
        int: 映射到0-1000范围内的整数值。如果角度超出定义范围，将被约束在边界值（0或1000）。
    """
    # 获取该手指的角度范围
    min_angle, max_angle = finger_dict[finger_name]

    mapped_value = int(((current_angle - min_angle) / (max_angle - min_angle)) * 1000)

    if mapped_value < 0:
        return 0
    elif mapped_value > 1000:
        return 1000
    else:
        return mapped_value


class HandDataPublisher:
    def __init__(self):
        self.ude_glove = UDEGloveSDK()
        self.ude_glove.initialize()
        self.ude_glove.start_listening()
        self.period = 0.04  # 25Hz

    def left_timer_callback(self):
        try:
            role_list = (
                self.ude_glove.get_role_name_list()
            )  # Get the list of role names
            # print("role_list", role_list)
            if len(role_list) > 0:
                print(f"left:-------------------------")
                for role_name in role_list:
                    finger_data = self.ude_glove.get_vec_finger_data(
                        role_name
                    )  # Get finger data
                    angle = [0] * 6
                    map_angle = [0] * 6

                    angle[0] = finger_data[0].x  # 大拇指向垂直于手掌方向移动
                    angle[1] = finger_data[2].x  # 大拇指指向平行于手掌方向移动
                    angle[2] = finger_data[3].x
                    angle[3] = finger_data[6].x
                    angle[4] = finger_data[9].x
                    angle[5] = finger_data[12].x

                    for i, ang in enumerate(angle):
                        finger_name = finger_names[i]
                        command = map_angle_to_value(finger_name, ang)
                        map_angle[i] = filtering(finger_name, command)

                    print(f"Angles: {angle}")
                    print(f"Published Mapped Values: {map_angle}")

        except Exception as e:
            print(f"Error: {e}")

    def right_timer_callback(self):
        try:
            role_list = (
                self.ude_glove.get_role_name_list()
            )  # Get the list of role names
            if len(role_list) > 0:
                print(f"right:-------------------------")
                for role_name in role_list:
                    finger_data = self.ude_glove.get_vec_finger_data(
                        role_name
                    )  # Get finger data
                    angle = [0] * 6
                    map_angle = [0] * 6

                    angle[0] = finger_data[15].x  # 大拇指向垂直于手掌方向移动
                    angle[1] = finger_data[17].x  # 大拇指指向平行于手掌方向移动
                    angle[2] = finger_data[18].x
                    angle[3] = finger_data[21].x
                    angle[4] = finger_data[24].x
                    angle[5] = finger_data[27].x

                    for i, ang in enumerate(angle):
                        finger_name = finger_names[i]
                        command = map_angle_to_value(finger_name, ang)
                        map_angle[i] = filtering(finger_name, command)

                    print(f"Angles: {angle}")
                    print(f"Published Mapped Values: {map_angle}")

        except Exception as e:
            print(f"Error: {e}")


def main():
    import time

    hand_data_publisher = HandDataPublisher()

    try:
        while True:
            hand_data_publisher.left_timer_callback()
            hand_data_publisher.right_timer_callback()
            time.sleep(0.04)
    except KeyboardInterrupt:
        pass
    finally:
        pass


if __name__ == "__main__":
    main()
