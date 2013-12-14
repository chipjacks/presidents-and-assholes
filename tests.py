import unittest
import common
import server
import client
import message
import socket
import logging
import time
import threading


class TestDeck(unittest.TestCase):
    def setUp(self):
        self.a_deck = common.Deck()

    def test_deal(self):
        for i in range(1,7):
            hands = self.a_deck.deal(i)
            self.assertEqual(len(hands), i)
            self.assertEqual(self.a_deck.DECK_SIZE, sum([len(h) for h in hands]))
            self.assertEqual(self.a_deck.DECK_SIZE // i, min([len(h) for h in hands]))
            if (i * self.a_deck.DECK_SIZE // i != self.a_deck.DECK_SIZE):
                self.assertEqual(self.a_deck.DECK_SIZE // i + 1, max([len(h) for h in hands]))

class TestPlayer(unittest.TestCase):
    def setUp(self):
        self.a_player = common.Player("Jim")

    def test_add_rem_from_hand(self):
        cards = [1,2,3,4,5,6,7,8]
        self.a_player.add_to_hand(cards)
        self.assertEqual(cards, self.a_player.hand)
        cards = [9,10]
        self.a_player.add_to_hand(cards)
        self.assertEqual([i for i in range(1,11)], self.a_player.hand)
        self.assertRaises(AssertionError, self.a_player.add_to_hand, [52,53])
        self.a_player.remove_from_hand(cards)
        self.assertEqual([i for i in range(1, 9)], self.a_player.hand)
        self.a_player.clear_hand()
        self.assertEqual([], self.a_player.hand)
        self.assertRaises(common.PlayerError, self.a_player.remove_from_hand, [1])

class TestTable(unittest.TestCase):
    def setUp(self):
        self.a_table = common.Table()

    def test_add_rem_players(self):
        players = [common.Player(i) for i in range(5)]
        for i in range(5):
            self.a_table.add_player(players[i])
        self.assertEqual(players, self.a_table.players)
        for i in range(5):
            self.a_table.remove_player(players[i])
        self.assertEqual([], self.a_table.players)
        
    def test_play_cards(self):
        players = [common.Player(i) for i in range(5)]
        # self.assertRaises(common.PlayerError, self.a_table.play_cards, players[0], [1,2])
        for i in range(5):
            self.a_table.add_player(players[i])
        players[0].add_to_hand([1,2])
        self.a_table.play_cards(players[0], [1,2])
        self.assertEqual(self.a_table.played_cards, [[1,2]])
        # self.assertRaises(common.PlayerError, self.a_table.play_cards, players[1], {1,2})
    

invalid_msgs = [
    'asd asdf asd',
    '[asdf asfa sdf',
    'asdfasdddddf]',
    'sjoin|chipjack]',
    '[sjoin|chipjack',
    '[sjoinchipjack]'
    ]

valid_cjoins = [
    '[cjoin|chipjack]',
    '[cjoin|hiprack ]',
    '[cjoin|lcp69   ]',    
    '[cjoin|chipple ]',    
    '[cjoin|nipple  ]',
    '[cjoin|ch8_px__]',
    '[cjoin|BillyBo ]',
    '[cjoin|bonnyho ]',
    '[cjoin|Tman    ]',
    '[cjoin|chipdrip]'
    ]

valid_sjoins = [
    '[sjoin|chipjack]'
    ]

invalid_cjoins = [
    '[cjoin|ch9|dsaf]',
    '[cjoin|chip ack]',
    '[cjoin|cs      ]',
    '[cjoin|asdfa]',
    '[cjoin|asdfdfs         ]'
    ]

class TestMessageHandling(unittest.TestCase):

    def setUp(self):
        pass

    def test_is_valid(self):
        for msg in valid_cjoins:
            self.assertTrue(message.is_valid(msg), msg)
        for msg in invalid_msgs:
            self.assertFalse(message.is_valid(msg), msg)
    
    def test_msg_type(self):
        for msg in valid_cjoins:
            self.assertEqual(message.msg_type(msg), 'cjoin')

    def test_fields(self):
        i = 0
        for field in message.fields('[cjoin|1|2|3|4|5|6|7]'):
            i += 1
            self.assertEqual(str(i), field)
        for field in message.fields('[cjoin||||]'):
            self.assertEqual('', field)

    def test_split_buffer_into_msgs(self):
        buff = '[this is a test][blah blah blah][unique newyork unique newyork]'
        msgs = message.split_buffer_into_msgs(buff)
        self.assertEqual(len(msgs), 3)
        self.assertEqual(msgs[0], '[this is a test]')
        self.assertEqual(msgs[1], '[blah blah blah]')
        self.assertEqual(msgs[2], '[unique newyork unique newyork]')

    def test_cards_to_str(self):
        cards = []
        self.assertEqual(message.cards_to_str(cards, 4), '52,52,52,52')
        self.assertEqual(message.cards_to_str(cards, 18), ('52,' * 18)[:-1])
        cards = [0]
        self.assertEqual(message.cards_to_str(cards, 4), '00,52,52,52')
        cards = [1,2]
        self.assertEqual(message.cards_to_str(cards, 4), '01,02,52,52')
        self.assertEqual(message.cards_to_str(cards, 2), '01,02')
        self.assertEqual(message.cards_to_str(cards, 18), '01,02,' + ('52,'*16)[:-1])

    def test_str_to_cards_to_str(self):
        card_str = '01,02,03,04,05,06,52,52,52'
        cards = message.str_to_cards(card_str)
        new_card_str = message.cards_to_str(cards, 9)
        self.assertEqual(card_str, new_card_str)

    def test_hand_to_msg_and_msg_to_hand(self):
        hand = [0,1,2,3,4,5]
        msg = message.hand_to_msg(hand)
        self.assertEqual(len(msg), 61)
        new_hand = message.msg_to_hand(msg)
        self.assertEqual(hand, new_hand)

    def test_table_to_stabl_and_stabl_to_player_list(self):
        table = common.Table()
        players = [common.Player(str(i)) for i in range(7)]
        for i in range(7):
            table.add_player(players[i])
        stabl = message.table_to_stabl(table)
        psl = message.stabl_to_player_stat_list(stabl)
        for i, player in enumerate(table.players):
            self.assertEqual(player.name, psl[i].name)
            self.assertEqual(psl[i].status, 'l')
            self.assertEqual(psl[i].num_cards, 0)
            self.assertEqual(psl[i].strikes, 0)

    def test_lobby_to_slobb_and_slobb_to_lobby(self):
        lobby = [common.Player(str(i)) for i in range(10)]
        slobb = message.lobby_to_slobb(lobby)
        new_lobby = message.slobb_to_lobby(slobb)
        self.assertEqual([p.name for p in lobby], new_lobby)

class TestNameMangling(unittest.TestCase):
    names = [
        'a',
        'a1',
        'a11',
        'a111',
        'herbert',
        '_',
        'herbert1'
    ]

    invalid_names = [
        '9asdf',
        '%asdfsad',
        'sdf$asd'
    ]

    def setUp(self):
        self.mangled_names = []
        pass

    def test_name_mangle(self):
        mangle_multiplier = 100
        for name in self.names + self.invalid_names:
            for i in range(0, mangle_multiplier):
                mangled_name = server.mangle_name(self.mangled_names,
                    name)
                self.mangled_names.append(mangled_name)
        self.mangled_names = set(self.mangled_names)
        self.assertEqual(len(self.mangled_names),
            mangle_multiplier * (len(self.names) + len(self.invalid_names)))

class TestClient():
    def __init__(self):
        HOST = 'localhost'
        PORT = 36789
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect((HOST, PORT))
        self.messages = []

    def send(self, msg):
        self.socket.sendall(bytes(msg, 'ascii'))

    def receive(self):
        if self.messages == []:
            buff = self.socket.recv(4096).decode('ascii')
            self.messages.append(messages.split_buffer_into_messages(buff))
        msg = self.messages[0]
        self.messages = self.messages[1:]
        return msg

    def close(self):
        self.socket.shutdown(socket.SHUT_RDWR)
        self.socket.close()

# class TestGameServer(unittest.TestCase):
#     def setUp(self): 
#         self.server, self.server_thread = server.start_server_in_thread()
#         self.clients = [TestClient() for i in range(20)]
# 
#     def test_gameplay(self):
#         i = 0
#         for cjoin in valid_cjoins:
#             self.clients[i].send(cjoin)
#             i += 1
#         time.sleep(0.1) # give the server a split second to process
#         self.assertTrue(server.table.full())
#         self.assertTrue(server.table.ready())
# 
#     def tearDown(self):
#         for client in self.clients:
#             client.close()
#         self.server.close()
#         self.server_thread.join()

def test_game(host, num_bots=6, gui=True):
    if not host:
        host = common.HOST

    names = [
        'chipjack',
        'hiprack ',
        'lcp69   ',
        'chipple ',
        'nipple  ',
        'ch8_px__',
        'BillyBo ',
        'bonnyho ',
        'Tman    ',
        'chipdrip',
        'yokie   ',
        'parsnip ',
        'yodeler ',
        'pikachu ',
        'mr_bean ',
        'turdhead',
        'rufus   '
        ]

    names += ['john' for i in range(50)]
    server_thread = threading.Thread(target=server.main, args=(['-s', host],))
    server_thread.start()
    if gui:
        my_client_thread = threading.Thread(target=client.main,
            args=(['-n', names[0], '-m'],))
        my_client_thread.start()
    client_threads = [threading.Thread(target=client.main, args=(['-n', name],))
        for name in names[1:num_bots+1]]
    for thread in client_threads:
        thread.start()

    if gui:
        my_client_thread.join()
    else:
        TEST_DURATION = 5
        print("Running {} sec automated game".format(TEST_DURATION))
        for i in range(TEST_DURATION):
            time.sleep(1)
            print(i+1)
        # cleanup
        server.stop()
        server_thread.join()
        print("Shutdown server")
        for thread in client_threads:
            thread.join(timeout=1)
        print("Shutdown clients")


if __name__ == '__main__':
    common.setup_logging()
    # unittest.main()
    h = '192.168.10.100'
    lh = 'localhost'
    GUI = True
    if not GUI:
        # speed test
        print("Performing automated test to see if game crashes")
        client.AUTOPLAY_PAUSE = 0
        test_game(lh, 60, gui=GUI)
    else:
        print("Starting GUI to test user interaction")
        time.sleep(.5)
        # gui test
        client.AUTOPLAY_PAUSE = .1
        test_game(lh, 10, gui=GUI)
    logging.info('Logging finished')
