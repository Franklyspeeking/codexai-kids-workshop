window.SEED = {
  "hero": "小禾",
  "partner": "圆圆",
  "theme": "森林奇遇",
  "current": "start",
  "path": [],
  "endings": [],
  "nodes": {
    "start": {
      "title": "第一幕 · 不会亮的灯塔",
      "text": "{hero}和伙伴{partner}来到森林灯塔。今晚的灯不亮了，而回家的小动物还在路上。地上留着一张地图和一把旧钥匙。",
      "choices": [
        {
          "label": "带上地图，两人一起去找守塔人",
          "next": "keeper"
        },
        {
          "label": "先用钥匙检查灯塔，两人保持同行",
          "next": "tower"
        }
      ]
    },
    "keeper": {
      "title": "第二幕 · 守塔人的难题",
      "text": "守塔人说：“灯塔需要大家一起转动齿轮。我只有一双手。”{hero}看了看{partner}，决定……",
      "choices": [
        {
          "label": "邀请附近的小动物一起合作",
          "next": "team"
        },
        {
          "label": "先查阅维护记录，找出问题原因",
          "next": "archive"
        }
      ]
    },
    "tower": {
      "title": "第二幕 · 黑暗里的声音",
      "text": "门开了，里面传来嘎吱声。{partner}有些害怕。{hero}想起约定：不使用暴力，也不让伙伴独自离开。",
      "choices": [
        {
          "label": "陪伙伴一起返回，留下求助标记",
          "next": "home"
        },
        {
          "label": "两人一起去寻找守塔人帮助",
          "next": "keeper"
        }
      ]
    },
    "team": {
      "title": "合作的灯光",
      "text": "{hero}和{partner}带来帮手，齿轮缓缓转动，灯塔亮了。",
      "lesson": "结局一：不是一个人无所不能，而是找到愿意一起行动的人。",
      "ending": true
    },
    "archive": {
      "title": "记录里的答案",
      "text": "{hero}和{partner}在记录中发现齿轮被落叶卡住。守塔人清理后，灯光重新照亮道路。",
      "lesson": "结局二：先观察和寻找证据，有时比急着行动更有效。",
      "ending": true
    },
    "home": {
      "title": "勇敢地暂停",
      "text": "{hero}陪{partner}返回安全的小屋，把灯塔的问题告诉了大人。第二天，他们一起回来修好灯塔。",
      "lesson": "结局三：知道何时暂停和求助，也是一种勇气。",
      "ending": true
    }
  }
};
