
import json
import sys
import logging
import numpy as np
from typing import List, Tuple, Dict, Optional
from collections import defaultdict, Counter
import pickle
import os

# ===========================================
# 机器学习相关
# ===========================================
# try:
#     import xgboost as xgb
#     XGBOOST_AVAILABLE = True
# except ImportError:
#     XGBOOST_AVAILABLE = False

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
        """计算向听数（简化版）"""
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


# ===========================================
# XGBoostPredictor
# ===========================================
# class XGBoostPredictor:
#     """XGBoost预测器"""
#
#     def __init__(self):
#         self.discard_model = None
#         self.is_trained = False
#         self.feature_dim = 200  # 特征维度
#
#         if XGBOOST_AVAILABLE:
#             self.discard_model = xgb.XGBClassifier(
#                 n_estimators=100,
#                 max_depth=6,
#                 learning_rate=0.1,
#                 random_state=42
#             )
#
#     def extract_features(self, game_state: dict) -> np.ndarray:
#         """提取特征向量"""
#         features = []
#
#         # 手牌特征 (34维 - 每种牌的数量)
#         hand_counter = Counter(game_state.get('hand', []))
#         for suit in ['B', 'T', 'W']:
#             for num in range(1, 10):
#                 features.append(hand_counter.get(f"{suit}{num}", 0))
#         for suit in ['F', 'J']:
#             for num in range(1, 4):
#                 features.append(hand_counter.get(f"{suit}{num}", 0))
#
#         # 牌池特征 (34维 - 每种牌的剩余数量)
#         pai_chi = game_state.get('pai_chi', [0] * 77)
#         for suit in ['B', 'T', 'W']:
#             for num in range(1, 10):
#                 tile_id = self._str2num(f"{suit}{num}")
#                 features.append(pai_chi[tile_id] if 0 < tile_id < len(pai_chi) else 0)
#         for suit in ['F', 'J']:
#             for num in range(1, 4):
#                 tile_id = self._str2num(f"{suit}{num}")
#                 features.append(pai_chi[tile_id] if 0 < tile_id < len(pai_chi) else 0)
#
#         # 游戏状态特征
#         features.extend([
#             game_state.get('ming_pai_cnt', 0),
#             game_state.get('gang_count', 0),
#             game_state.get('feng_quan', 0),
#             len(game_state.get('hand', [])),
#         ])
#
#         # 填充到固定长度
#         while len(features) < self.feature_dim:
#             features.append(0)
#
#         return np.array(features[:self.feature_dim])
#
#     def _str2num(self, card: str) -> int:
#         """字符串牌转数字编码"""
#         if len(card) != 2:
#             return -1
#
#         card_type = card[0]
#         num = int(card[1])
#
#         if card_type == 'B':
#             return num
#         elif card_type == 'T':
#             return 20 + num
#         elif card_type == 'W':
#             return 40 + num
#         elif card_type == 'F':
#             return 59 + 2 * num
#         elif card_type == 'J':
#             return 69 + 2 * num
#         else:
#             return -1
#
#     def predict_discard(self, game_state: dict, candidates: List[str]) -> str:
#         """预测最佳弃牌"""
#         if not self.is_trained or not XGBOOST_AVAILABLE:
#             return candidates[0] if candidates else "B1"
#
#         features = self.extract_features(game_state)
#
#         # 为每个候选牌计算得分
#         best_card = candidates[0]
#         best_score = float('-inf')
#
#         for card in candidates:
#             # 创建假设弃牌后的状态
#             temp_state = game_state.copy()
#             temp_hand = temp_state.get('hand', []).copy()
#             if card in temp_hand:
#                 temp_hand.remove(card)
#             temp_state['hand'] = temp_hand
#
#             temp_features = self.extract_features(temp_state)
#             score = self.discard_model.predict_proba([temp_features])[0][1]  # 假设标签1代表好的选择
#
#             if score > best_score:
#                 best_score = score
#                 best_card = card
#
#         return best_card
#
#     def load_model(self, model_path: str):
#         """加载训练好的模型"""
#         if os.path.exists(model_path) and XGBOOST_AVAILABLE:
#             self.discard_model.load_model(model_path)
#             self.is_trained = True

class EnhancedMahjongAI:
    """增强版麻将AI"""

    def __init__(self):
        # 继承原有功能
        self.my_id = 0
        self.feng_quan = 0
        self.hand = []
        self.packs = []
        self.pai_chi = [0] * 77
        self.ming_pai_cnt = 0
        self.pai_wall = [21, 21, 21, 21]
        self.gang_count = 0
        self.turn_count = 0

        # 新增功能
        self.efficiency_calculator = HandEfficiencyCalculator()
        self.opponent_analyzer = OpponentAnalyzer()
        # self.xgb_predictor = XGBoostPredictor()  # 已注释掉

        # 策略权重（可动态调整）
        self.strategy_weights = {
            'offensive': 0.4,
            'defensive': 0.3,
            'efficiency': 0.3
        }

        # ===========================================
        # 机器学习模型加载已
        # ===========================================
        # 尝试加载预训练模型
        # self.xgb_predictor.load_model("mahjong_discard_model.xgb")

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

    def str2num(self, card: str) -> int:
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
            card_num = self.str2num(card)
            if 0 < card_num < len(self.pai_chi):
                if self.pai_chi[card_num] == 0:
                    score -= 100  # 牌池中没有了，优先打出
                else:
                    score += self.pai_chi[card_num] * 5  # 剩余越多价值越高

            # 2.4 特殊牌型评分
            if card[0] in ['F', 'J']:  # 风牌箭牌
                score -= 10  # 稍微降低价值

            card_scores[card] = score

        # ===========================================
        # XGBoost预测
        # ===========================================
        # # 3. XGBoost预测
        # if self.xgb_predictor.is_trained:
        #     xgb_choice = self.xgb_predictor.predict_discard(game_state, list(card_scores.keys()))
        #     if xgb_choice in card_scores:
        #         card_scores[xgb_choice] += 20  # 给XGBoost推荐的牌加分

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
            self.opponent_analyzer.update_discard(self.my_id, card, self.turn_count)
            logging.debug(f"打出牌: {card}")

    def my_draw(self, card: str):
        """摸牌"""
        self.hand.append(card)
        if self.str2num(card) > 0:
            self.pai_chi[self.str2num(card)] -= 1
        logging.debug(f"摸牌: {card}")

    def process_opponent_action(self, player_id: int, action: str, details: str):
        """处理对手行为"""
        if action == "PLAY":
            self.opponent_analyzer.update_discard(player_id, details, self.turn_count)
            if self.str2num(details) > 0:
                self.pai_chi[self.str2num(details)] -= 1

        self.opponent_analyzer.update_action(player_id, action, {'details': details, 'turn': self.turn_count})

    def check_hu(self, win_tile: str = None) -> Tuple[bool, int]:
        """检查胡牌"""
        try:
            if len(self.hand) != 13:
                return False, 0

            if not win_tile and self.hand:
                win_tile = self.hand[-1]
                test_hand = self.hand[:-1]
            else:
                test_hand = self.hand.copy()

            fans = MahjongFanCalculator(
                pack=tuple(self.packs),
                hand=tuple(test_hand),
                winTile=win_tile,
                flowerCount=0,
                isSelfDrawn=True,
                is4thTile=False,
                isAboutKong=self.gang_count > 0,
                isWallLast=False,
                seatWind=self.my_id,
                prevalentWind=self.feng_quan
            )

            fan_cnt = sum(f[0] * f[1] for f in fans)
            return fan_cnt >= 8, fan_cnt

        except Exception as e:
            logging.error(f"胡牌检查失败: {str(e)}")
            return False, 0

    def process_request(self, request: str) -> str:
        """处理请求（沿用原有逻辑，但使用增强决策）"""
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

                # 胡牌检查
                can_hu, fan_count = self.check_hu(card)
                if can_hu:
                    return json.dumps({"response": "HU", "debug": f"Enhanced win: {fan_count} fans", "data": ""})

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

                        # 胡牌检查
                        can_hu, fan_count = self.check_hu(card)
                        if can_hu:
                            return json.dumps(
                                {"response": "HU", "debug": f"Enhanced win by discard: {fan_count}", "data": ""})

                        # 其他动作检查...
                        #to do

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