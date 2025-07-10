
import json
import sys
import logging
import numpy as np
from typing import List, Tuple, Dict, Optional
from collections import defaultdict, Counter
import pickle
import os

# 设置日志
logging.basicConfig(level=logging.DEBUG)

try:
    from MahjongGB import MahjongFanCalculator
except ImportError:
    def MahjongFanCalculator(*args, **kwargs):
        return [(8, 1)]


class HandEfficiencyCalculator:
    """手牌效率计算器"""

    @staticmethod
    def calculate_shanten(hand_counter: Counter) -> int:
        """计算向听数"""
        pairs = sum(1 for count in hand_counter.values() if count >= 2)
        triplets = sum(count // 3 for count in hand_counter.values())

        # 简化计算：理想情况下需要4个面子+1个雀头
        needed_sets = 4 - triplets
        available_pairs = pairs

        if available_pairs > 0:
            needed_sets -= 1  # 一个对子作为雀头
            available_pairs -= 1

        # 考虑顺子可能性
        shun_potential = HandEfficiencyCalculator._count_sequential_potential(hand_counter)
        needed_sets -= min(needed_sets, shun_potential)

        return max(0, needed_sets)

    @staticmethod
    def _count_sequential_potential(hand_counter: Counter) -> int:
        """计算顺子潜力"""
        potential = 0
        for suit in ['B', 'T', 'W']:
            for i in range(1, 8):
                cards = [f"{suit}{i}", f"{suit}{i + 1}", f"{suit}{i + 2}"]
                min_count = min(hand_counter[card] for card in cards)
                potential += min_count
        return potential


class OpponentAnalyzer:
    """对手分析器"""

    def __init__(self):
        self.discard_history = defaultdict(list)
        self.action_history = defaultdict(list)
        self.danger_tiles = defaultdict(set)

    def update_discard(self, player_id: int, tile: str, turn: int):
        """更新弃牌记录"""
        self.discard_history[player_id].append((tile, turn))

    def update_action(self, player_id: int, action: str, context: dict):
        """更新行为记录"""
        self.action_history[player_id].append({
            'action': action,
            'context': context,
            'turn': len(self.action_history[player_id])
        })

    def assess_danger_level(self, tile: str, current_turn: int) -> float:
        """评估某张牌的危险程度"""
        danger_score = 0.0

        for player_id in range(4):
            if player_id == 0:  # 跳过自己
                continue

            recent_discards = [t for t, turn in self.discard_history[player_id]
                               if current_turn - turn <= 3]

            # 如果最近没有打出相同花色的牌，危险度增加
            if tile[0] in ['B', 'T', 'W']:
                same_suit_discards = [t for t in recent_discards if t[0] == tile[0]]
                if not same_suit_discards:
                    danger_score += 0.3

                # 检查是否可能形成顺子
                tile_num = int(tile[1])
                for offset in [-2, -1, 1, 2]:
                    adj_tile = f"{tile[0]}{tile_num + offset}"
                    if adj_tile in recent_discards:
                        danger_score += 0.2

            # 风牌箭牌的危险度评估
            elif tile[0] in ['F', 'J']:
                if tile not in recent_discards:
                    danger_score += 0.4

        return min(1.0, danger_score)


class EnhancedMahjongAI:
    """增强版麻将AI """

    def __init__(self):
        self.my_id = 0
        self.feng_quan = 0
        self.hand = []
        self.packs = []
        self.pai_chi = [0] * 77
        self.ming_pai_cnt = 0
        self.pai_wall = [21, 21, 21, 21]
        self.gang_count = 0
        self.turn_count = 0
        #添加一套新的手牌管理
        self.shoupai=[0]*77

        self.efficiency_calculator = HandEfficiencyCalculator()
        self.opponent_analyzer = OpponentAnalyzer()

        # 策略权重（可动态调整）
        self.strategy_weights = {
            'offensive': 0.4,
            'defensive': 0.3,
            'efficiency': 0.3
        }

        self._init_pai_chi()

    def _init_pai_chi(self):
        """初始化牌池"""
        for i in range(1, 10):
            self.pai_chi[i] = 4
        for i in range(21, 30):
            self.pai_chi[i] = 4
        for i in range(41, 50):
            self.pai_chi[i] = 4
        for i in range(61, 68, 2):
            self.pai_chi[i] = 4
        for i in range(71, 76, 2):
            self.pai_chi[i] = 4

    def strTonum(self, card: str) -> int:
        """字符串牌转数字编码"""
        if len(card) != 2:
            return -1

        card_type = card[0]
        num = int(card[1])

        if card_type == 'B':
            return num
        elif card_type == 'T':
            return 20 + num
        elif card_type == 'W':
            return 40 + num
        elif card_type == 'F':
            return 59 + 2 * num
        elif card_type == 'J':
            return 69 + 2 * num
        else:
            return -1

    def is_my_shangjia(self, player_id: int) -> bool:
        """判断是否为上家"""
        return (player_id + 1) % 4 == self.my_id

    def can_form_shunzi(self, card: str) -> List[str]:
        """检查能否形成顺子，返回可能的中间牌"""
        if len(card) != 2 or card[0] not in ['B', 'T', 'W']:
            return []

        card_num = self.strTonum(card)
        if card_num == -1:
            return []

        hand_counter = Counter(self.hand)
        possible_middle = []

        # 检查三种顺子可能: ABC, BAC, CAB (A是card)
        suit = card[0]
        num = int(card[1])

        # 作为顺子的左牌 (card, card+1, card+2)
        if num <= 7:
            left_card = f"{suit}{num + 1}"
            right_card = f"{suit}{num + 2}"
            if hand_counter[left_card] > 0 and hand_counter[right_card] > 0:
                possible_middle.append(left_card)

        # 作为顺子的中牌 (card-1, card, card+1)
        if 2 <= num <= 8:
            left_card = f"{suit}{num - 1}"
            right_card = f"{suit}{num + 1}"
            if hand_counter[left_card] > 0 and hand_counter[right_card] > 0:
                possible_middle.append(card)

        # 作为顺子的右牌 (card-2, card-1, card)
        if num >= 3:
            left_card = f"{suit}{num - 2}"
            middle_card = f"{suit}{num - 1}"
            if hand_counter[left_card] > 0 and hand_counter[middle_card] > 0:
                possible_middle.append(middle_card)

        return possible_middle

    def evaluate_action_value(self, action: str, card: str) -> float:
        """评估动作价值"""
        if action == "PASS":
            return 0.0

        # 模拟执行动作后的手牌状态
        temp_hand = self.hand.copy()
        temp_counter = Counter(temp_hand)

        if action == "PENG":
            # 移除两张相同的牌
            if temp_counter[card] >= 2:
                temp_hand.remove(card)
                temp_hand.remove(card)
                temp_counter = Counter(temp_hand)
        elif action == "CHI":
            # 这里简化处理，实际需要更复杂的逻辑
            pass
        elif action == "GANG":
            # 移除三张相同的牌
            if temp_counter[card] >= 3:
                for _ in range(3):
                    temp_hand.remove(card)
                temp_counter = Counter(temp_hand)

        # 计算向听数改变
        current_shanten = self.efficiency_calculator.calculate_shanten(Counter(self.hand))
        new_shanten = self.efficiency_calculator.calculate_shanten(temp_counter)

        # 向听数减少越多，价值越高
        shanten_value = (current_shanten - new_shanten) * 10

        # 增加明牌数量的负面影响
        ming_penalty = -2 if action in ["PENG", "CHI"] else 0

        return shanten_value + ming_penalty

    def get_game_state(self) -> dict:
        """获取当前游戏状态"""
        return {
            'hand': self.hand.copy(),
            'packs': self.packs.copy(),
            'pai_chi': self.pai_chi.copy(),
            'ming_pai_cnt': self.ming_pai_cnt,
            'gang_count': self.gang_count,
            'feng_quan': self.feng_quan,
            'turn_count': self.turn_count
        }

    def check_hu(self, win_tile: str, is_self_drawn: bool) -> Tuple[bool, int]:
        """修复后的胡牌检查函数"""
        try:
            # 根据是否自摸来决定手牌状态
            if is_self_drawn:
                # 自摸：使用除去摸到牌外的13张手牌
                if len(self.hand) < 14:
                    return False, 0
                test_hand = [card for card in self.hand if card != win_tile]
                if len(test_hand) < 13:
                    return False, 0
                test_hand = test_hand[:13]  # 确保是13张
            else:
                # 荣和：使用当前13张手牌
                if len(self.hand) != 13:
                    return False, 0
                test_hand = self.hand.copy()

            # 计算是否为绝张或杠上
            is_4th_tile = self.pai_chi[self.strTonum(win_tile)] == 0 if self.strTonum(win_tile) > 0 else False

            # 检查是否为海底/河底
            next_player = (self.my_id + 1) % 4 if not is_self_drawn else self.my_id
            is_wall_last = self.pai_wall[next_player] == 0

            fans = MahjongFanCalculator(
                pack=tuple(self.packs),
                hand=tuple(test_hand),
                winTile=win_tile,
                flowerCount=0,
                isSelfDrawn=is_self_drawn,
                is4thTile=is_4th_tile,
                isAboutKong=self.gang_count > 0,
                isWallLast=is_wall_last,
                seatWind=self.my_id,
                prevalentWind=self.feng_quan
            )

            fan_cnt = sum(f[0] * f[1] for f in fans)

            logging.debug(f"胡牌检查: {win_tile}, 自摸:{is_self_drawn}, 番数:{fan_cnt}, 手牌数:{len(test_hand)}")
            return fan_cnt >= 8, fan_cnt

        except Exception as e:
            logging.error(f"胡牌检查失败: {str(e)}")
            return False, 0

    def enhanced_decide_abandon_card(self) -> str:
        """增强版弃牌决策"""
        if not self.hand:
            return "B1"

        self.turn_count += 1

        # 获取当前游戏状态
        game_state = self.get_game_state()

        # 1. 基础候选牌筛选
        hand_counter = Counter(self.hand)
        candidates = []

        # 优先考虑单张牌
        for card, count in hand_counter.items():
            if count == 1:
                candidates.append(card)

        # 如果没有单张，考虑多余的牌
        if not candidates:
            for card, count in hand_counter.items():
                if count > 1:
                    candidates.append(card)

        if not candidates:
            candidates = self.hand.copy()

        # 2. 多维度评分
        card_scores = {}

        for card in set(candidates):  # 去重
            if card not in self.hand:
                continue

            score = 0

            # 2.1 效率评分
            temp_hand = self.hand.copy()
            temp_hand.remove(card)
            temp_counter = Counter(temp_hand)
            shanten = self.efficiency_calculator.calculate_shanten(temp_counter)
            score += (8 - shanten) * 10  # 向听数越小越好

            # 2.2 安全评分
            danger = self.opponent_analyzer.assess_danger_level(card, self.turn_count)
            score -= danger * 50  # 危险度越高扣分越多

            # 2.3 牌池评分
            card_num = self.strTonum(card)
            if 0 < card_num < len(self.pai_chi):
                if self.pai_chi[card_num] == 0:
                    score -= 100  # 牌池中没有了，优先打出
                else:
                    score += self.pai_chi[card_num] * 5  # 剩余越多价值越高

            # 2.4 特殊牌型评分
            if card[0] in ['F', 'J']:  # 风牌箭牌
                score -= 10  # 稍微降低价值

            card_scores[card] = score

        # 4. 选择得分最低的牌（因为我们要丢弃）
        if card_scores:
            best_card = min(card_scores.keys(), key=lambda x: card_scores[x])
            logging.debug(f"增强弃牌决策: {best_card}, 得分: {card_scores[best_card]}")
            return best_card

        return self.hand[0]

    def my_play(self, card: str):
        """打出牌时更新对手分析"""
        if card in self.hand:
            self.hand.remove(card)
            card_num = self.strTonum(card)
            if card_num>0:
                self.shoupai[card_num] += 1
            self.opponent_analyzer.update_discard(self.my_id, card, self.turn_count)
            logging.debug(f"打出牌: {card}")

    def my_draw(self, card: str):
        """摸牌"""
        self.hand.append(card)
        card_num = self.strTonum(card)
        if card_num>0:
            self.pai_chi[card_num] -= 1
            self.shoupai[card_num] += 1
        # if self.strTonum(card) > 0:
        #     self.pai_chi[self.strTonum(card)] -= 1
        logging.debug(f"摸牌: {card}")

    def process_opponent_action(self, player_id: int, action: str, details: str):
        """处理对手行为"""
        if action == "PLAY":
            self.opponent_analyzer.update_discard(player_id, details, self.turn_count)
            if self.strTonum(details) > 0:
                self.pai_chi[self.strTonum(details)] -= 1

        self.opponent_analyzer.update_action(player_id, action, {'details': details, 'turn': self.turn_count})

    def process_request(self, request: str) -> str:
        """处理请求（修复胡牌逻辑）"""
        try:
            parts = request.split()

            if not parts:
                return json.dumps({"response": "PASS", "debug": "Empty request", "data": ""})

            if parts[0] == "0":  # 初始化
                self.my_id = int(parts[1])
                self.feng_quan = int(parts[2])
                return json.dumps({"response": "PASS", "debug": f"Enhanced Init: ID={self.my_id}", "data": ""})

            elif parts[0] == "1":  # 初始手牌
                self.hand = []
                for i in range(5, min(18, len(parts))):
                    self.my_draw(parts[i])
                return json.dumps(
                    {"response": "PASS", "debug": f"Enhanced initial hand: {len(self.hand)} cards", "data": ""})

            elif parts[0] == "2":  # 摸牌
                card = parts[1]
                self.my_draw(card)
                self.pai_wall[self.my_id] -= 1

                # 修复后的胡牌检查 - 自摸
                can_hu, fan_count = self.check_hu(card, is_self_drawn=True)
                if can_hu:
                    return json.dumps(
                        {"response": "HU", "debug": f"Enhanced self-draw win: {fan_count} fans", "data": ""})

                # 杠牌检查
                hand_counter = Counter(self.hand)
                for card_name, count in hand_counter.items():
                    if count == 4:
                        self.hand = [c for c in self.hand if c != card_name]
                        self.packs.append(("GANG", card_name, 0))
                        self.gang_count += 1
                        return json.dumps({"response": f"GANG {card_name}", "debug": "Enhanced dark kong", "data": ""})

                # 使用增强弃牌决策
                abandon_card = self.enhanced_decide_abandon_card()
                self.my_play(abandon_card)
                return json.dumps(
                    {"response": f"PLAY {abandon_card}", "debug": f"Enhanced discard: {abandon_card}", "data": ""})

            elif parts[0] == "3":  # 其他玩家动作
                player_id = int(parts[1])
                event = parts[2]

                if event == "PLAY" and len(parts) > 3:
                    card = parts[3]

                    if player_id != self.my_id:
                        self.process_opponent_action(player_id, event, card)

                        # 修复后的胡牌检查 - 荣和
                        can_hu, fan_count = self.check_hu(card, is_self_drawn=False)
                        if can_hu:
                            return json.dumps(
                                {"response": "HU", "debug": f"Enhanced win by discard: {fan_count} fans", "data": ""})

                        # 其他动作检查（吃碰杠）
                        hand_counter = Counter(self.hand)

                        # 1. 检查是否能杠牌 (需要手中有3张相同的牌)
                        if hand_counter[card] >= 3:
                            action_value = self.evaluate_action_value("GANG", card)
                            if action_value > 0:  # 如果杠牌有价值
                                return json.dumps({"response": "GANG", "debug": f"Enhanced gang: {card}", "data": ""})

                        # 2. 检查风牌/箭牌能否碰
                        if card[0] in ['F', 'J'] and hand_counter[card] >= 2:
                            action_value = self.evaluate_action_value("PENG", card)
                            if action_value > 0 or self.ming_pai_cnt >= 1:  # 如果碰牌有价值或已有明牌
                                # 模拟碰牌后的弃牌决策
                                temp_hand = self.hand.copy()
                                temp_hand.remove(card)
                                temp_hand.remove(card)
                                temp_old_hand = self.hand
                                self.hand = temp_hand
                                abandon_card = self.enhanced_decide_abandon_card()
                                self.hand = temp_old_hand
                                return json.dumps(
                                    {"response": f"PENG {abandon_card}", "debug": f"Enhanced peng FJ: {card}",
                                     "data": ""})

                        # 3. 检查是否能吃（仅限上家的数字牌）
                        if self.is_my_shangjia(player_id) and card[0] in ['B', 'T', 'W']:
                            possible_middles = self.can_form_shunzi(card)
                            if possible_middles:
                                action_value = self.evaluate_action_value("CHI", card)
                                if action_value > 0 or self.ming_pai_cnt >= 1:
                                    # 选择最优的顺子组合
                                    best_middle = possible_middles[0]  # 简化处理，选择第一个

                                    # 模拟吃牌后的弃牌决策
                                    temp_hand = self.hand.copy()
                                    temp_hand.append(card)

                                    # 移除顺子中的其他两张牌
                                    card_num = int(card[1])
                                    middle_num = int(best_middle[1])
                                    suit = card[0]

                                    if middle_num == card_num + 1:  # card是左牌
                                        temp_hand.remove(best_middle)  # 中牌
                                        temp_hand.remove(f"{suit}{card_num + 2}")  # 右牌
                                    elif middle_num == card_num:  # card是中牌
                                        temp_hand.remove(f"{suit}{card_num - 1}")  # 左牌
                                        temp_hand.remove(f"{suit}{card_num + 1}")  # 右牌
                                    else:  # card是右牌
                                        temp_hand.remove(f"{suit}{card_num - 2}")  # 左牌
                                        temp_hand.remove(best_middle)  # 中牌

                                    temp_old_hand = self.hand
                                    self.hand = temp_hand
                                    abandon_card = self.enhanced_decide_abandon_card()
                                    self.hand = temp_old_hand
                                    return json.dumps({"response": f"CHI {best_middle} {abandon_card}",
                                                       "debug": f"Enhanced chi: {card}", "data": ""})

                        # 4. 检查数字牌是否能碰
                        if card[0] in ['B', 'T', 'W'] and hand_counter[card] >= 2:
                            action_value = self.evaluate_action_value("PENG", card)
                            if action_value > 0 or self.ming_pai_cnt >= 1:
                                # 模拟碰牌后的弃牌决策
                                temp_hand = self.hand.copy()
                                temp_hand.remove(card)
                                temp_hand.remove(card)
                                temp_old_hand = self.hand
                                self.hand = temp_hand
                                abandon_card = self.enhanced_decide_abandon_card()
                                self.hand = temp_old_hand
                                return json.dumps(
                                    {"response": f"PENG {abandon_card}", "debug": f"Enhanced peng num: {card}",
                                     "data": ""})

                return json.dumps({"response": "PASS", "debug": "Enhanced processing", "data": ""})

            return json.dumps({"response": "PASS", "debug": "Enhanced no action", "data": ""})

        except Exception as e:
            logging.error(f"增强处理请求失败: {str(e)}")
            return json.dumps({"response": "PASS", "debug": f"Enhanced error: {str(e)}", "data": ""})


def main():
    """主函数"""
    ai = EnhancedMahjongAI()

    try:
        line = input().strip()
        response = ai.process_request(line)
        print(response)
        sys.stdout.flush()

        print(">>>BOTZONE_REQUEST_KEEP_RUNNING<<<")
        sys.stdout.flush()

        while True:
            try:
                line = input().strip()
                if not line:
                    break

                response = ai.process_request(line)
                print(response)
                sys.stdout.flush()

                print(">>>BOTZONE_REQUEST_KEEP_RUNNING<<<")
                sys.stdout.flush()

            except EOFError:
                break
            except Exception as e:
                error_response = json.dumps({
                    "response": "PASS",
                    "debug": f"Enhanced error: {str(e)}",
                    "data": ""
                })
                print(error_response)
                sys.stdout.flush()
                break

    except Exception as e:
        error_response = json.dumps({
            "response": "PASS",
            "debug": f"Enhanced fatal error: {str(e)}",
            "data": ""
        })
        print(error_response)
        sys.stdout.flush()


if __name__ == "__main__":
    main()