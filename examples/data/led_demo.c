\
/* STC89C52RC LED 流水灯 + 按键中断示例 */

#include <reg52.h>

/* 硬件连接定义 */
#define LED_PORT P1
sbit KEY1 = P3^2;  /* INT0 按键 */
sbit KEY2 = P3^3;  /* INT1 按键 */
sbit BUZZER = P2^3;

/* 全局变量 */
unsigned char led_pattern = 0x01;
unsigned char led_direction = 0;  /* 0=左移, 1=右移 */
unsigned int delay_ms_count = 0;

/* 延时函数 */
void delay_ms(unsigned int ms) {
    unsigned int i, j;
    for (i = 0; i < ms; i++)
        for (j = 0; j < 120; j++);
}

/* 定时器0初始化 - 1ms定时 (11.0592MHz) */
void Timer0_Init(void) {
    TMOD &= 0xF0;
    TMOD |= 0x01;      /* 模式1: 16位定时器 */
    TH0 = 0xFC;         /* 初值高字节 */
    TL0 = 0x66;         /* 初值低字节 */
    ET0 = 1;             /* 允许T0中断 */
    TR0 = 1;             /* 启动T0 */
}

/* 外部中断0初始化 - 下降沿触发 */
void INT0_Init(void) {
    IT0 = 1;             /* 下降沿触发 */
    EX0 = 1;             /* 允许INT0中断 */
    PX0 = 1;             /* INT0高优先级 */
}

/* 外部中断1初始化 - 下降沿触发 */
void INT1_Init(void) {
    IT1 = 1;
    EX1 = 1;
}

/* 串口初始化 - 9600bps (11.0592MHz) */
void UART_Init(void) {
    SCON = 0x50;         /* 模式1, 允许接收 */
    TMOD &= 0x0F;
    TMOD |= 0x20;       /* T1模式2: 8位自动重装 */
    TH1 = 0xFD;          /* 9600bps */
    TL1 = 0xFD;
    TR1 = 1;
    ES = 1;              /* 允许串口中断 */
}

/* 串口发送一个字节 */
void UART_SendByte(unsigned char dat) {
    SBUF = dat;
    while (!TI);
    TI = 0;
}

/* 串口发送字符串 */
void UART_SendString(char *str) {
    while (*str) {
        UART_SendByte(*str++);
    }
}

/* 主函数 */
void main(void) {
    Timer0_Init();
    INT0_Init();
    INT1_Init();
    UART_Init();
    EA = 1;              /* 开总中断 */

    UART_SendString("STC89C52RC Ready\\r\\n");

    while (1) {
        LED_PORT = ~led_pattern;
        delay_ms(200);

        if (led_direction == 0) {
            led_pattern <<= 1;
            if (led_pattern == 0) led_pattern = 0x01;
        } else {
            led_pattern >>= 1;
            if (led_pattern == 0) led_pattern = 0x80;
        }
    }
}

/* 定时器0中断服务函数 */
void Timer0_ISR(void) interrupt 1 {
    TH0 = 0xFC;
    TL0 = 0x66;
    delay_ms_count++;
}

/* 外部中断0服务函数 - 切换流水灯方向 */
void INT0_ISR(void) interrupt 0 {
    delay_ms(20);        /* 消抖 */
    if (KEY1 == 0) {
        led_direction = !led_direction;
        BUZZER = 0;
        delay_ms(50);
        BUZZER = 1;
    }
}

/* 外部中断1服务函数 - 暂停/恢复 */
void INT1_ISR(void) interrupt 2 {
    delay_ms(20);
    if (KEY2 == 0) {
        TR0 = !TR0;      /* 切换定时器运行状态 */
    }
}

/* 串口中断服务函数 */
void UART_ISR(void) interrupt 4 {
    unsigned char recv;
    if (RI) {
        RI = 0;
        recv = SBUF;
        UART_SendByte(recv);  /* 回显 */
    }
}
