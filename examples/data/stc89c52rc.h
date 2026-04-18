/* STC89C52RC 寄存器定义 */

/* 中断相关寄存器 */
#define IE_ADDR     0xA8
#define IE_EA       (1 << 7)
#define IE_ET2      (1 << 5)
#define IE_ES       (1 << 4)
#define IE_ET1      (1 << 3)
#define IE_EX1      (1 << 2)
#define IE_ET0      (1 << 1)
#define IE_EX0      (1 << 0)

#define IP_ADDR     0xB8
#define IP_PT2      (1 << 5)
#define IP_PS       (1 << 4)
#define IP_PT1      (1 << 3)
#define IP_PX1      (1 << 2)
#define IP_PT0      (1 << 1)
#define IP_PX0      (1 << 0)

/* 定时器寄存器 */
#define TCON_ADDR   0x88
#define TCON_TF1    (1 << 7)
#define TCON_TR1    (1 << 6)
#define TCON_TF0    (1 << 5)
#define TCON_TR0    (1 << 4)
#define TCON_IE1    (1 << 3)
#define TCON_IT1    (1 << 2)
#define TCON_IE0    (1 << 1)
#define TCON_IT0    (1 << 0)

#define TMOD_ADDR   0x89
#define TMOD_GATE1  (1 << 7)
#define TMOD_CT1    (1 << 6)
#define TMOD_M1_1   (1 << 5)
#define TMOD_M0_1   (1 << 4)
#define TMOD_GATE0  (1 << 3)
#define TMOD_CT0    (1 << 2)
#define TMOD_M1_0   (1 << 1)
#define TMOD_M0_0   (1 << 0)

/* 串口寄存器 */
#define SCON_ADDR   0x98
#define SCON_SM0    (1 << 7)
#define SCON_SM1    (1 << 6)
#define SCON_SM2    (1 << 5)
#define SCON_REN    (1 << 4)
#define SCON_TB8    (1 << 3)
#define SCON_RB8    (1 << 2)
#define SCON_TI     (1 << 1)
#define SCON_RI     (1 << 0)

#define PCON_ADDR   0x87
#define PCON_SMOD   (1 << 7)
#define PCON_SMOD0  (1 << 6)
#define PCON_GF1    (1 << 3)
#define PCON_GF0    (1 << 2)
#define PCON_PD     (1 << 1)
#define PCON_IDL    (1 << 0)

/* 看门狗寄存器 */
#define WDT_CONTR_ADDR  0xE1
#define WDT_EN_WDT      (1 << 5)
#define WDT_CLR_WDT     (1 << 4)
#define WDT_IDLE_WDT    (1 << 3)

/* GPIO 端口地址 */
#define P0_ADDR     0x80
#define P1_ADDR     0x90
#define P2_ADDR     0xA0
#define P3_ADDR     0xB0

/* P3 口第二功能位定义 */
#define P3_RXD      (1 << 0)
#define P3_TXD      (1 << 1)
#define P3_INT0     (1 << 2)
#define P3_INT1     (1 << 3)
#define P3_T0       (1 << 4)
#define P3_T1       (1 << 5)
#define P3_WR       (1 << 6)
#define P3_RD       (1 << 7)

/* EEPROM/IAP 寄存器 */
#define ISP_DATA    0xE2
#define ISP_ADDRH   0xE3
#define ISP_ADDRL   0xE4
#define ISP_CMD     0xE5
#define ISP_TRIG    0xE6
#define ISP_CONTR   0xE7

typedef struct {
    unsigned char TL0;
    unsigned char TH0;
    unsigned char TL1;
    unsigned char TH1;
} TimerRegs;

void Timer0_Init(void) {
    TMOD &= 0xF0;
    TMOD |= 0x01;
    TH0 = 0xFC;
    TL0 = 0x66;
    TR0 = 1;
    ET0 = 1;
    EA = 1;
}

void UART_Init(unsigned char baud_reload) {
    SCON = 0x50;
    TMOD &= 0x0F;
    TMOD |= 0x20;
    TH1 = baud_reload;
    TL1 = baud_reload;
    TR1 = 1;
    ES = 1;
    EA = 1;
}
